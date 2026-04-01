import json
import os

def filter_relations_by_round(file_path, target_round):
    """
    筛选在指定回合 x 之前（包含 x）创建的关系。
    """
    filtered_data = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                # 解析每一行的 JSON 数据
                relation_data = json.loads(line)
                
                # 获取关系的开始回合
                start_round = relation_data.get('start_round', 9999)
                
                # 判断条件：开始回合必须小于等于目标回合
                if start_round <= target_round:
                    filtered_data.append(relation_data)
                    
            except json.JSONDecodeError:
                continue
                
    return filtered_data

# --- 使用示例 ---

x = 50  # 假设当前是第 50 回合
result = filter_relations_by_round(r'C:\Users\ziyji\project\SOS\examples\deduction\data\raw\relation.jsonl', x)

# 打印结果统计
print(f"在第 {x} 回合及之前建立的关系总数: {len(result)}")

# 打印前 5 条结果作为示例
print(f"--- 筛选结果示例 (前5条) ---")
for rel in result[:5]:
    print(json.dumps(rel, ensure_ascii=False))

# 如需保存到新文件
output_path = r'C:\Users\ziyji\project\SOS\examples\deduction\data\relations\relations.jsonl'
# 创建目录（如果不存在）
os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, 'w', encoding='utf-8') as f_out:
    for rel in result:
        f_out.write(json.dumps(rel, ensure_ascii=False) + '\n')