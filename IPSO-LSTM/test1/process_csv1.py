import pandas as pd
import os

# 自动创建 data 文件夹，避免保存报错
os.makedirs('data', exist_ok=True)

# 1. 读取评论数据（按你真实路径）
df = pd.read_csv('weibo_comment/weibo_comment.csv', encoding='utf-8-sig')

# 2. 按评论ID去重（保留第一次出现）
df = df.drop_duplicates(subset='评论ID', keep='first')

# 3. 转换时间格式 → 改成你 CSV 里真实列名：创建时间
df['时间'] = pd.to_datetime(df['发布时间'], errors='coerce')

# 4. 提取日期和小时
df['时间'] = df['时间'].dt.strftime('%Y-%m-%d %H')


# 5. 按【日期 + 小时】分组统计
daily_hour_stats = df.groupby(['时间']).agg(
    评论数=('评论ID', 'count'),
    # 点赞数=('点赞数', 'sum')
).reset_index()

# 6. 排序
daily_hour_stats = daily_hour_stats.sort_values(['时间']).reset_index(drop=True)

# 7. 保存结果（统一文件名）
daily_hour_stats.to_csv('data/time_hourly_statistics2_1.csv', index=False, encoding='utf-8-sig')

# 8. 输出信息
print("✅ 每日每小时统计完成（已按评论ID去重）！")
print(f"去重后总评论数：{len(df)}")
print(f"前10行结果预览：\n{daily_hour_stats.head(10)}")
print(f"📊 总共有 {len(daily_hour_stats)} 个时间分段")
print("💾 文件已保存：data/time_hourly_statistics2_1.csv")