"""
繁體中文轉換模組
將簡體中文轉換為繁體中文，並提供檢測功能
"""

import re
import logging
from opencc import OpenCC

logger = logging.getLogger(__name__)

# 自訂字元映射：處理 OpenCC 可能轉換不正確的字
custom_mappings = {
    '里': '裡',
    '为': '為',
    '着': '著',
    '账': '帳',
    '了': '了',
    '个': '個',
}

# 手動映射：將不常用的繁體字轉換為常用的
manual_mappings = {
    '瞭解': '了解',
    '羣': '群',
    '臺': '台',
    '峯': '峰',
}

# 初始化 OpenCC 轉換器 (簡體轉繁體)
_cc = OpenCC('s2t')


def is_simplified_chinese(char: str) -> bool:
    """
    檢查單個字元是否為簡體中文
    透過比較轉換前後是否相同來判斷
    """
    if not re.match(r'[\u4e00-\u9fff]', char):
        return False
    converted = _cc.convert(char)
    return converted != char


def contains_simplified(text: str) -> bool:
    """
    檢查文字中是否包含簡體中文
    
    Args:
        text: 要檢查的文字
        
    Returns:
        True 如果包含簡體中文，否則 False
    """
    # 提取所有中文字元
    chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
    
    for char in chinese_chars:
        if is_simplified_chinese(char):
            return True
    
    return False


def is_all_traditional(text: str) -> bool:
    """
    檢查文字是否全部為繁體中文（不包含簡體中文）
    
    Args:
        text: 要檢查的文字
        
    Returns:
        True 如果全部為繁體中文，否則 False
    """
    return not contains_simplified(text)


def convert_to_traditional(text: str) -> str:
    """
    將文字轉換為繁體中文
    
    Args:
        text: 要轉換的文字（可能包含簡體中文）
        
    Returns:
        轉換後的繁體中文文字
    """
    if not text:
        return text
    
    # 先用 OpenCC 進行基本轉換
    converted = _cc.convert(text)
    
    # 套用自訂映射
    for simplified, traditional in custom_mappings.items():
        converted = converted.replace(simplified, traditional)
    
    # 套用手動映射（處理不常用的繁體字）
    for unusual, common in manual_mappings.items():
        converted = converted.replace(unusual, common)
    
    return converted


def convert_if_needed(text: str) -> tuple[str, bool]:
    """
    檢查文字是否需要轉換，如果需要則進行轉換
    
    Args:
        text: 要檢查和可能轉換的文字
        
    Returns:
        tuple: (轉換後的文字, 是否有進行轉換)
    """
    if not text:
        return text, False
    
    if is_all_traditional(text):
        logger.debug("Text is already in Traditional Chinese, no conversion needed")
        return text, False
    
    converted = convert_to_traditional(text)
    logger.info(f"Converted text from Simplified to Traditional Chinese")
    return converted, True


# 方便直接作為模組使用的別名
convert = convert_to_traditional
check = is_all_traditional

