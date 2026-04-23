
import pandas as pd
from datetime import datetime
import os

# 指定CSV文件路径
file_path = 'weibo_comment/weibo_comment1.csv'  # 修改为您的文件路径

# 检查文件是否存在
if not os.path.exists(file_path):
    print(f"错误：文件 '{file_path}' 不存在！")
    exit()

# 读取CSV文件
try:
    df = pd.read_csv(file_path, encoding='utf-8')
except UnicodeDecodeError:
    try:
        df = pd.read_csv(file_path, encoding='gbk')
    except UnicodeDecodeError:
        try:
            df = pd.read_csv(file_path, encoding='utf-8-sig')
        except Exception as e:
            print(f"读取文件时出错：{e}")
            exit()

# 查找时间列
time_column = None
for col in df.columns:
    if '时间' in col or 'Time' in col or 'time' in col:
        time_column = col
        break

if not time_column:
    print("未找到时间列")
    exit()

# 定义时间格式转换函数
def convert_time_format(time_str):
    try:
        # 将原格式转换为datetime对象
        dt = datetime.strptime(str(time_str), "%a %b %d %H:%M:%S %z %Y")
        # 转换为新格式: 2025-12-11 13
        return dt.strftime("%Y-%m-%d %H")
    except Exception as e:
        return None

# 转换时间格式并提取年月日小时
hour_times = []
for time_str in df[time_column]:
    converted_time = convert_time_format(time_str)
    if converted_time:
        hour_times.append(converted_time)
    else:
        dt = datetime.strptime(str(time_str), "%Y-%m-%d %H:%M:%S")
        hour_times.append(dt.strftime("%Y-%m-%d %H"))
# 统计每个小时的数量
hour_counts = {}
for hour in hour_times:
    if hour in hour_counts:
        hour_counts[hour] += 1
    else:
        hour_counts[hour] = 1

# 转换为DataFrame并排序
result_df = pd.DataFrame({
    '时间': list(hour_counts.keys()),
    '数量': list(hour_counts.values())
})

# 按时间排序
result_df = result_df.sort_values('时间')

# 输出结果
print("时间统计结果：")
print("=" * 30)
for _, row in result_df.iterrows():
    print(f"{row['时间']}:00 | 数量: {row['数量']}")

print(f"\n总共 {len(hour_times)} 条记录")
print(f"统计时间段数: {len(result_df)}")

# 保存结果到CSV文件
output_file = 'data/time_hourly_statistics1.csv'
result_df.to_csv(output_file, index=False, encoding='utf-8-sig')
print(f"\n统计结果已保存到: {output_file}")