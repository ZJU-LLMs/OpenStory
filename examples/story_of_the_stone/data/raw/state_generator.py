import json
import hashlib

def generate_encoded_id(record):
    """
    Generate a unique encoded ID (first 8 characters of MD5 Hash).
    """
    unique_str = f"{record.get('家族', '')}_{record.get('姓名', '')}_{record.get('出现回合', '')}"
    return hashlib.md5(unique_str.encode('utf-8')).hexdigest()[:8].upper()

def filter_data_latest_residence(file_path, target_round):
    """
    Filter surviving characters:
    - Residence: Extract the latest location string at or before the current round (no longer keep round number and list format).
    - Field management: Keep all keys in FIELDS_TO_KEEP, fill with default value if missing or empty.
    """
    processed_data = []
    
    # --- Configuration area: Field name mapping (original field name -> new field name) ---
    # If a field doesn't need to be renamed, it can be omitted from this config, or set to the same name
    FIELD_NAME_MAPPING = {
        "姓名": "id",
        "健康": "health",
        "职务": "duty",
        "权力": "right",
    }
    
    # --- Configuration area: Key name is the field, key value is the corresponding custom default value ---
    # Note: The key name here is the original field name (used when reading from input data), and will be mapped according to FIELD_NAME_MAPPING during output
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
                
                # 1. Survival judgment
                is_alive = False
                if appear_round <= target_round:
                    if death_round == -1 or death_round > target_round:
                        is_alive = True
                
                if is_alive:
                    # 2. Generate encoded ID
                    enc_id = generate_encoded_id(record)
                    
                    # 3. Preprocessing: Filter 'Residence' (Core modification point: convert to string)
                    residence_data = record.get('居住地', [])
                    residence_str = "" # Default is empty
                    
                    if isinstance(residence_data, list):
                        # Filter out records from the current round and before
                        valid_residences = [
                            item for item in residence_data 
                            if isinstance(item, dict) and item.get('回合', 9999) <= target_round
                        ]
                        
                        if valid_residences:
                            # Find the one with the largest round number
                            latest_item = max(valid_residences, key=lambda item: item.get('回合', -1))
                            
                            # Try to extract the location name string (try common key names: 'Location', 'Place', 'Residence')
                            # If there is no clear key, take the first non-"round" string value in the dictionary
                            residence_str = latest_item.get('地点') or latest_item.get('居住地') or latest_item.get('场所')
                            
                            if not residence_str:
                                for k, v in latest_item.items():
                                    if k != '回合' and isinstance(v, str):
                                        residence_str = v
                                        break
                    elif isinstance(residence_data, str):
                        residence_str = residence_data
                    
                    record['居住地'] = residence_str

                    # 4. Preprocessing: Filter 'Major Node' (Keep all history at or before the current round)
                    events = record.get('重大节点', [])
                    if isinstance(events, list):
                        record['重大节点'] = [
                            e for e in events 
                            if isinstance(e, dict) and e.get('回合', 9999) <= target_round
                        ]

                    # 5. Build final data (Fill default values and save)
                    new_record = {'id': enc_id}
                    
                    for field_name, default_val in FIELDS_TO_KEEP.items():
                        # Get value from original record (using original field name)
                        value = record.get(field_name)
                        
                        # Get mapped field name (if mapping is configured, use new name; otherwise use original name)
                        output_field_name = FIELD_NAME_MAPPING.get(field_name, field_name)
                        
                        # Determine empty value: None, "", [], {} are all considered as needing default values
                        if value is None or value == "" or value == [] or value == {}:
                            new_record[output_field_name] = default_val
                        else:
                            new_record[output_field_name] = value
                    
                    processed_data.append(new_record)
                    
            except json.JSONDecodeError:
                continue
                
    print(f"Processing complete. {len(FIELDS_TO_KEEP)} fields retained according to configuration, empty values automatically filled with default values.")
    return processed_data

# --- Usage Example ---
if __name__ == "__main__":
    current_round = 50
    input_file = r''
    output_file = r''
    
    result = filter_data_latest_residence(input_file, current_round)

    with open(output_file, 'w', encoding='utf-8') as f_out:
        for char in result:
            f_out.write(json.dumps(char, ensure_ascii=False) + '\n')
