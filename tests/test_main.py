from src.flyai_crawler import FlyAICrawler, FlyAITrainCrawler
from src.spring_crawler import SpringCrawler
from main import create_crawler


def test_create_flyai_crawler():
    assert isinstance(create_crawler("flyai"), FlyAICrawler)


def test_create_flyai_train_crawler():
    assert isinstance(create_crawler("flyai_train"), FlyAITrainCrawler)


def test_create_spring_crawler():
    assert isinstance(create_crawler("spring"), SpringCrawler)
