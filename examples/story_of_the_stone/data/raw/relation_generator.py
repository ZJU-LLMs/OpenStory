import json
import os

def filter_relations_by_round(file_path, target_round):
    """
    Filter relationships created before or at the specified round x.
    """
    filtered_data = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                # Parse JSON data for each line
                relation_data = json.loads(line)
                
                # Get the start round of the relationship
                start_round = relation_data.get('start_round', 9999)
                
                # Condition: start round must be less than or equal to target round
                if start_round <= target_round:
                    filtered_data.append(relation_data)
                    
            except json.JSONDecodeError:
                continue
                
    return filtered_data

# --- Usage Example ---

x = 50  # Assume current round is 50
result = filter_relations_by_round(r'', x)

# Print result statistics
print(f"Total relationships established at or before round {x}: {len(result)}")

# Print first 5 results as an example
print(f"--- Filter Results Example (First 5) ---")
for rel in result[:5]:
    print(json.dumps(rel, ensure_ascii=False))

# If you need to save to a new file
output_path = r''
# Create directory (if it does not exist)
os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, 'w', encoding='utf-8') as f_out:
    for rel in result:
        f_out.write(json.dumps(rel, ensure_ascii=False) + '\n')
