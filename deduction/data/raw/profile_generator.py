import json
import hashlib

def generate_encoded_id(record):
    """
    生成唯一编码 ID (MD5 Hash 前8位)。
    """
    unique_str = f"{record.get('家族', '')}_{record.get('姓名', '')}_{record.get('出现回合', '')}"
    return hashlib.md5(unique_str.encode('utf-8')).hexdigest()[:8].upper()

def filter_data_latest_residence(file_path, target_round):
    """
    筛选存活角色：
    - 字段管理：仅保留指定的非空字段。
    - 居住地：只保留当前回合及之前最新的一个地点。
    - 重大节点：保留当前回合及之前的所有历史事件。
    """
    processed_data = []
    
    # --- 配置区：在此定义需要保留的字段名称 ---
    # 键为原文件字段名，值为输出后的字段名（如果想重命名可以修改值）
    FIELDS_TO_KEEP = {
        "姓名": "id",
    }
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                
                appear_round = record.get('出现回合', 9999)
                death_round = record.get('死亡回合', -1)
                
                # 1. 存活判定
                is_alive = False
                if appear_round <= target_round:
                    if death_round == -1 or death_round > target_round:
                        is_alive = True
                
                if is_alive:
                    # 2. 生成编码 ID
                    enc_id = generate_encoded_id(record)
                    
                    # 3. 处理 '居住地' (只取最新)
                    residence = record.get('居住地', [])
                    if isinstance(residence, list):
                        valid_residences = [
                            item for item in residence 
                            if item.get('回合', 9999) <= target_round
                        ]
                        if valid_residences:
                            latest = max(valid_residences, key=lambda item: item.get('回合', -1))
                            record['居住地'] = [latest]
                        else:
                            record['居住地'] = []

                    # 4. 处理 '重大节点' (保留历史)
                    events = record.get('重大节点', [])
                    if isinstance(events, list):
                        record['重大节点'] = [
                            e for e in events 
                            if e.get('回合', 9999) <= target_round
                        ]

                    # 5. 构建最终数据 (核心修改点)
                    # 逻辑：首先放入 ID，然后遍历白名单，仅当原数据存在且非空时写入
                    new_record = {'code': enc_id}
                    
                    for orig_key, target_key in FIELDS_TO_KEEP.items():
                        value = record.get(orig_key)
                        
                        # 判定非空：不是 None, 且不是空字符串、空列表、空字典
                        if value is not None and value != "" and value != [] and value != {}:
                            new_record[target_key] = value
                    
                    processed_data.append(new_record)
                    
            except json.JSONDecodeError:
                continue
                
    return processed_data

# --- 使用示例 (路径保持你提供的原样) ---
if __name__ == "__main__":
    x = 50
    raw_path = r'C:\Users\ziyji\project\SOS\examples\deduction\data\raw\database.jsonl'
    out_path = r'C:\Users\ziyji\project\SOS\examples\deduction\data\agents\profiles.jsonl'
    
    result = filter_data_latest_residence(raw_path, x)

    with open(out_path, 'w', encoding='utf-8') as f_out:
        for char in result:
            f_out.write(json.dumps(char, ensure_ascii=False) + '\n')
            
    print(f"处理完成，共计 {len(result)} 个存活角色已保存。")