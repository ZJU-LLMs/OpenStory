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
    - 居住地：提取当前回合及之前最新的地点字符串（不再保留回合数和列表格式）。
    - 字段管理：保留 FIELDS_TO_KEEP 中的所有键，缺失或为空则填充默认值。
    """
    processed_data = []
    
    # --- 配置区：字段名映射 (原始字段名 -> 新字段名) ---
    # 如果某个字段不需要重命名，可以不在此配置中，或设置为相同的名称
    FIELD_NAME_MAPPING = {
        "姓名": "id",
        "健康": "health",
        "职务": "duty",
        "权力": "right",
    }
    
    # --- 配置区：键名为字段，键值为对应的自定义默认值 ---
    # 注意：这里的键名是原始字段名（从输入数据中读取时使用），输出时会根据 FIELD_NAME_MAPPING 进行映射
    FIELDS_TO_KEEP = {
        "姓名": "",        
        "健康": 5,
        "职务": "",
        "权力": 0,        
        "energy": 100,
        "fullness": 100,
        "mood": 100,
        "emotion": "",
        "items": [],
        "master": ""
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
                    
                    # 3. 预处理：过滤 '居住地' (核心修改点：转为字符串)
                    residence_data = record.get('居住地', [])
                    residence_str = "" # 默认为空
                    
                    if isinstance(residence_data, list):
                        # 筛选出当前回合及以前的记录
                        valid_residences = [
                            item for item in residence_data 
                            if isinstance(item, dict) and item.get('回合', 9999) <= target_round
                        ]
                        
                        if valid_residences:
                            # 找到回合数最大的那一条
                            latest_item = max(valid_residences, key=lambda item: item.get('回合', -1))
                            
                            # 尝试提取地点名称字符串 (尝试常见的键名：'地点', '场所', '居住地')
                            # 如果没有明确的键，则取字典中第一个非“回合”的字符串值
                            residence_str = latest_item.get('地点') or latest_item.get('居住地') or latest_item.get('场所')
                            
                            if not residence_str:
                                for k, v in latest_item.items():
                                    if k != '回合' and isinstance(v, str):
                                        residence_str = v
                                        break
                    elif isinstance(residence_data, str):
                        residence_str = residence_data
                    
                    record['居住地'] = residence_str

                    # 4. 预处理：过滤 '重大节点' (保留当前回合及之前的所有历史)
                    events = record.get('重大节点', [])
                    if isinstance(events, list):
                        record['重大节点'] = [
                            e for e in events 
                            if isinstance(e, dict) and e.get('回合', 9999) <= target_round
                        ]

                    # 5. 构建最终数据 (填充默认值并保存)
                    new_record = {'id': enc_id}
                    
                    for field_name, default_val in FIELDS_TO_KEEP.items():
                        # 从原始记录中获取值（使用原始字段名）
                        value = record.get(field_name)
                        
                        # 获取映射后的字段名（如果配置了映射，使用新名称；否则使用原名称）
                        output_field_name = FIELD_NAME_MAPPING.get(field_name, field_name)
                        
                        # 判定空值：None, "", [], {} 均视为需要使用默认值
                        if value is None or value == "" or value == [] or value == {}:
                            new_record[output_field_name] = default_val
                        else:
                            new_record[output_field_name] = value
                    
                    processed_data.append(new_record)
                    
            except json.JSONDecodeError:
                continue
                
    print(f"处理完成。已根据配置保留 {len(FIELDS_TO_KEEP)} 个字段，空值已自动填充默认值。")
    return processed_data

# --- 使用示例 ---
if __name__ == "__main__":
    current_round = 50
    input_file = r'C:\Users\ziyji\project\SOS\examples\deduction\data\raw\database.jsonl'
    output_file = r'C:\Users\ziyji\project\SOS\examples\deduction\data\agents\states.jsonl'
    
    result = filter_data_latest_residence(input_file, current_round)

    with open(output_file, 'w', encoding='utf-8') as f_out:
        for char in result:
            f_out.write(json.dumps(char, ensure_ascii=False) + '\n')