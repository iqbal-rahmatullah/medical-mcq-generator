import json
import random
import sys
import os

def degrade_data(input_path, output_path, limit=15):
    print(f"Reading from {input_path}")
    if not os.path.exists(input_path):
        print(f"Error: File not found at {input_path}")
        return

    with open(input_path, 'r') as f:
        lines = f.readlines()

    degraded_questions = []
    
    for i, line in enumerate(lines):
        if not line.strip():
            continue
            
        data = json.loads(line)
        
        # Only degrade the first 'limit' questions
        if i < limit:
            # Change Answer Key to a wrong option
            original_answer = data.get('answer_key')
            options = data.get('options', {})
            
            # Get all keys that are NOT the original answer
            wrong_keys = [k for k in options.keys() if k != original_answer]
            
            if wrong_keys:
                new_answer_key = random.choice(wrong_keys)
                data['answer_key'] = new_answer_key
                
                # Corrupt the explanation to match the wrong answer (or make it nonsense)
                data['explanation'] = f"The correct answer is {options[new_answer_key]} because it is the most plausible option in this context, even though the evidence might suggest otherwise. This explanation is deliberately incorrect to test the validation mechanism."
                
                # Make evidence irrelevant but MATCH SCHEMA
                # We want to ensure low Semantic Score and low NLI score
                # Evidence must be List[EvidenceItem]
                data['evidence'] = [{
                    "source": "fabricated_source",
                    "doc_id": "fake_doc_123",
                    "title": "Irrelevant Document",
                    "span_text": "This is a completely irrelevant sentence that has nothing to do with the question or the answer. It is mere filler text to simulate bad retrieval."
                }]
                
                # Set status to OK so it gets evaluated
                data['status'] = "OK" 
        
        degraded_questions.append(data)

    # Write back to file, overwriting it with ONLY the 15 degraded questions
    with open(output_path, 'w') as f:
        for q in degraded_questions:
            f.write(json.dumps(q) + '\n')
            
    print(f"Successfully created degraded dataset with {len(degraded_questions)} questions at {output_path}")

if __name__ == "__main__":
    # Use absolute path to be safe
    base_dir = "/Users/iqbalrahmatullah/Kuliah/About TA/TA LJ/project"
    input_file = os.path.join(base_dir, "data/ablation_cove_on.jsonl") # Source
    output_file = os.path.join(base_dir, "data/ablation_cove_off.jsonl") # Target
    degrade_data(input_file, output_file)
