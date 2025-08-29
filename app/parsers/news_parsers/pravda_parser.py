from typing import List, Optional
from datetime import datetime, timezone
from bs4 import BeautifulSoup
import re
import logging

from app.parsers.news_parsers.base_news_parser import BaseNewsParser
from app.models.news import NewsCollection, NewsItem, ArticleData


class PravdaNewsParser(BaseNewsParser):
    pass