"""
打码服务集成 - 支持超级鹰等平台
"""

import base64
import hashlib
import json
import logging
import random
from typing import Optional

logger = logging.getLogger(__name__)


class ChaojiyingClient:
    """超级鹰打码服务客户端"""

    def __init__(self, username: str, password: str, soft_id: str = "96001"):
        self.username = username
        self.password = password
        self.soft_id = soft_id
        self.base_url = "http://upload.chaojiying.net/Upload/Processing.php"

    def _get_password_hash(self) -> str:
        """获取密码的MD5哈希"""
        return hashlib.md5(self.password.encode()).hexdigest()

    async def solve_slider(self, image_base64: str) -> Optional[int]:
        """
        解决滑块验证码

        Args:
            image_base64: 图片的base64编码（不含data:image/png;base64,前缀）

        Returns:
            缺口的x坐标，失败返回None
        """
        try:
            import aiohttp

            params = {
                "user": self.username,
                "pass2": self._get_password_hash(),
                "softid": self.soft_id,
                "codetype": "9101",  # 滑块验证码类型
                "file_base64": image_base64,
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.base_url,
                    data=params,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    result_text = await resp.text()

            try:
                result = json.loads(result_text)
            except json.JSONDecodeError:
                logger.warning("[captcha] 超级鹰返回非JSON: %s", result_text[:100])
                return None

            # 检查错误码
            if result.get("err_no") != 0:
                logger.warning("[captcha] 超级鹰错误: %s", result.get("err_str", "未知错误"))
                return None

            # 解析坐标 pic_str 格式: "x,y" 或 "x1,y1|x2,y2"
            pic_str = result.get("pic_str", "")
            if not pic_str:
                logger.warning("[captcha] 超级鹰未返回坐标")
                return None

            # 取第一个坐标的x值
            if "|" in pic_str:
                pic_str = pic_str.split("|")[0]

            x = int(pic_str.split(",")[0])
            logger.info("[captcha] 超级鹰识别成功: x=%s", x)
            return x

        except Exception as e:
            logger.warning("[captcha] 超级鹰调用失败: %s", e)
            return None


class CaptchaSolver:
    """打码服务管理器"""

    def __init__(self, config: dict = None):
        """
        Args:
            config: 配置字典，包含:
                - type: 服务类型 ("chaojiying" 或 "none")
                - chaojiying_username: 超级鹰用户名
                - chaojiying_password: 超级鹰密码
                - chaojiying_soft_id: 超级鹰软件ID
        """
        self.config = config or {}
        self._chaojiying = None

    @property
    def chaojiying(self) -> Optional[ChaojiyingClient]:
        """获取超级鹰客户端"""
        if self._chaojiying is None:
            username = self.config.get("chaojiying_username")
            password = self.config.get("chaojiying_password")
            soft_id = self.config.get("chaojiying_soft_id", "96001")

            if username and password:
                self._chaojiying = ChaojiyingClient(username, password, soft_id)
                logger.info("[captcha] 超级鹰客户端已初始化")
            else:
                logger.debug("[captcha] 超级鹰未配置")

        return self._chaojiying

    async def solve_slider(self, page) -> Optional[int]:
        """
        解决滑块验证码

        Args:
            page: Playwright页面对象

        Returns:
            缺口的x坐标，失败返回None
        """
        # 获取验证码图片
        image_base64 = await self._get_captcha_image(page)
        if not image_base64:
            logger.warning("[captcha] 无法获取验证码图片")
            return None

        # 使用超级鹰
        if self.chaojiying:
            return await self.chaojiying.solve_slider(image_base64)

        return None

    async def _get_captcha_image(self, page) -> Optional[str]:
        """获取验证码图片的base64编码"""
        try:
            # 尝试获取canvas图片
            result = await page.evaluate("""
                () => {
                    // 尝试获取背景canvas
                    const canvas = document.querySelector(
                        '#aliyunCaptcha-canvas, .aliyunCaptcha-canvas canvas, canvas'
                    );
                    if (canvas && canvas.toDataURL) {
                        return canvas.toDataURL('image/png');
                    }
                    return null;
                }
            """)

            if result and result.startswith("data:image"):
                # 去掉前缀
                return result.split(",", 1)[1]

            return None

        except Exception as e:
            logger.warning("[captcha] 获取图片失败: %s", e)
            return None


# 全局打码服务实例
_solver: Optional[CaptchaSolver] = None


def init_captcha_solver(config: dict):
    """初始化全局打码服务"""
    global _solver
    _solver = CaptchaSolver(config)
    logger.info("[captcha] 打码服务已初始化: type=%s", config.get("type", "none"))


def get_captcha_solver() -> Optional[CaptchaSolver]:
    """获取全局打码服务"""
    return _solver
