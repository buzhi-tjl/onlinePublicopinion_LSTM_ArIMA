import pandas as pd
import numpy as np
import re
import chardet
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

def detect_file_encoding(file_path):
    """检测文件编码格式"""
    print("正在检测文件编码...")
    with open(file_path, 'rb') as f:
        raw_data = f.read(10000)  # 读取前10000字节用于检测
        result = chardet.detect(raw_data)
    print(f"检测结果：编码={result['encoding']}，置信度={result['confidence']:.4f}")
    return result['encoding']

def read_csv_with_correct_encoding(file_path):
    """自动选择正确编码读取CSV文件"""
    # 先检测编码
    detected_encoding = detect_file_encoding(file_path)
    
    # 尝试编码列表，优先级从检测结果到常见中文编码
    encoding_list = [detected_encoding, 'gbk', 'gb2312', 'utf-8', 'utf-8-sig']
    
    for encoding in encoding_list:
        if encoding is None:
            continue
        try:
            df = pd.read_csv(file_path, encoding=encoding)
            print(f"成功使用 [{encoding}] 编码读取文件")
            return df
        except Exception as e:
            print(f"使用 [{encoding}] 编码失败：{str(e)[:50]}")
            continue
    
    raise ValueError("所有编码尝试失败，请检查文件格式")

def extract_time_from_text(text):
    """从文本中提取时间（格式：12月01日 20:54 → 2024-12-01 20:54:00）"""
    if pd.isna(text):
        return None
    
    # 正则匹配日期（x月x日）和时间（x:x）
    time_pattern = r'(\d{1,2}月\d{1,2}日)\s+(\d{1,2}:\d{2})'
    match = re.search(time_pattern, str(text))
    
    if not match:
        return None
    
    date_str, time_str = match.groups()
    full_time_str = f"2024年{date_str} {time_str}"  # 假设年份为2024，可根据实际调整
    
    try:
        return datetime.strptime(full_time_str, '%Y年%m月%d日 %H:%M')
    except:
        return None

def hourly_analysis_main(input_csv_path, output_csv_path='按小时统计的舆情数量.csv', year=2024):
    """
    舆情数据按小时统计主函数
    :param input_csv_path: 输入CSV文件路径
    :param output_csv_path: 输出CSV文件路径
    :param year: 时间数据中的年份（默认2024）
    :return: 小时统计结果DataFrame
    """
    print("="*50)
    print("舆情数据按小时统计程序启动")
    print("="*50)
    
    # 1. 读取数据
    print("\n【步骤1：读取原始数据】")
    df = read_csv_with_correct_encoding(input_csv_path)
    print(f"原始数据规模：{df.shape[0]}行 × {df.shape[1]}列")
    print(f"原始数据列名：{df.columns.tolist()}")
    
    # 2. 提取时间信息
    print("\n【步骤2：提取时间信息】")
    if '字段4_文本' not in df.columns:
        raise ValueError("未找到'字段4_文本'列，请确认数据格式是否正确")
    
    df['提取时间'] = df['字段4_文本'].apply(extract_time_from_text)
    df_valid = df.dropna(subset=['提取时间']).copy()
    
    print(f"时间提取成功：{len(df_valid)}/{len(df)} 条记录（成功率：{len(df_valid)/len(df)*100:.1f}%）")
    if len(df_valid) == 0:
        raise ValueError("没有成功提取到任何时间信息，无法继续统计")
    
    # 3. 按小时分组统计
    print("\n【步骤3：按小时统计舆情数量】")
    # 生成小时级时间戳（取每小时起始时间）
    df_valid['小时时间'] = df_valid['提取时间'].dt.floor('H')
    
    # 统计每小时评论数量
    hourly_stats = df_valid.groupby('小时时间').size().reset_index(name='舆情数量')
    
    # 按时间排序
    hourly_stats = hourly_stats.sort_values('小时时间').reset_index(drop=True)
    
    # 重命名列名（符合需求：时间列（按小时划分）、舆情数量）
    hourly_stats.rename(columns={'小时时间': '时间列（按小时划分）'}, inplace=True)
    
    # 4. 输出统计信息
    print("\n【步骤4：统计结果汇总】")
    print(f"时间范围：{hourly_stats['时间列（按小时划分）'].min()} ~ {hourly_stats['时间列（按小时划分）'].max()}")
    print(f"统计小时数：{len(hourly_stats)} 小时")
    print(f"总舆情数量：{hourly_stats['舆情数量'].sum()} 条")
    print(f"平均每小时：{hourly_stats['舆情数量'].mean():.2f} 条")
    print(f"最高峰值：{hourly_stats['舆情数量'].max()} 条/小时（{hourly_stats.loc[hourly_stats['舆情数量'].idxmax(), '时间列（按小时划分）']}）")
    
    # 5. 保存结果
    print("\n【步骤5：保存结果文件】")
    hourly_stats.to_csv(output_csv_path, index=False, encoding='utf-8-sig')
    print(f"结果已保存至：{output_csv_path}")
    print(f"输出文件包含 {len(hourly_stats)} 行统计数据")
    
    print("\n" + "="*50)
    print("程序执行完成！")
    print("="*50)
    
    return hourly_stats

# ------------------- 执行入口 -------------------
if __name__ == "__main__":
    # 请根据实际文件路径修改以下参数
    INPUT_FILE_PATH = "./数据集.csv"    # 输入CSV文件路径
    OUTPUT_FILE_PATH = "./按小时统计的舆情数量.csv"  # 输出CSV文件路径
    TARGET_YEAR = 2024  # 时间数据中的年份（根据实际数据调整）
    
    # 执行小时统计
    result_df = hourly_analysis_main(
        input_csv_path=INPUT_FILE_PATH,
        output_csv_path=OUTPUT_FILE_PATH,
        year=TARGET_YEAR
    )
    
    # 打印前10条结果预览
    print("\n【结果预览（前10条）】")
    print(result_df.head(10).to_string(index=False))