#!/usr/bin/env python3
"""
Quality Evaluation for AI Model Outputs
Analyzes correctness, coherence, and reasoning quality
"""

import json
import re
from datetime import datetime
from typing import Dict, List, Tuple

class QualityEvaluator:
    """Evaluates the quality of model outputs"""
    
    def __init__(self):
        self.results = {}
    
    def evaluate_math_reasoning(self, output: str) -> Dict[str, any]:
        """Evaluate math problem solution"""
        score = 0
        feedback = []
        
        # Check for correct answer ($65.32)
        if '$65.32' in output or '65.32' in output:
            score += 3
            feedback.append("Correct final answer")
        elif '$65' in output or '65' in output:
            score += 1
            feedback.append("Approximate answer only")
        else:
            feedback.append("Answer not clearly stated")
        
        # Check for step-by-step reasoning
        steps = ['30%', 'discount', '$85', 'tax', '8%', 'calculation']
        steps_found = sum(1 for step in steps if step.lower() in output.lower())
        score += min(steps_found, 3)
        
        if steps_found >= 4:
            feedback.append("Complete step-by-step reasoning")
        elif steps_found >= 2:
            feedback.append("Partial reasoning shown")
        else:
            feedback.append("Limited reasoning")
        
        # Check for clarity
        if len(output.split('.')) >= 3:
            score += 1
            feedback.append("Multiple sentences (clear explanation)")
        
        return {
            "score": min(score, 10),
            "max_score": 10,
            "feedback": feedback,
            "has_correct_answer": '$65.32' in output or '65.32' in output
        }
    
    def evaluate_logic_deduction(self, output: str) -> Dict[str, any]:
        """Evaluate logic puzzle solution"""
        score = 0
        feedback = []
        
        # Check for correct solution
        # Alice = Teacher, Bob = Doctor, Carol = Engineer
        correct_assignments = [
            ('alice', 'teacher'),
            ('bob', 'doctor'),
            ('carol', 'engineer')
        ]
        
        correct_count = 0
        for person, profession in correct_assignments:
            if person.lower() in output.lower() and profession.lower() in output.lower():
                correct_count += 1
        
        score += correct_count * 2
        
        if correct_count == 3:
            feedback.append("All assignments correct")
        elif correct_count >= 1:
            feedback.append(f"{correct_count}/3 assignments correct")
        else:
            feedback.append("Assignments unclear")
        
        # Check reasoning
        reasoning_markers = ['clue', 'because', 'therefore', 'since', 'not']
        reasoning_found = sum(1 for m in reasoning_markers if m in output.lower())
        score += min(reasoning_found, 3)
        
        if reasoning_found >= 3:
            feedback.append("Strong logical reasoning")
        elif reasoning_found >= 1:
            feedback.append("Some reasoning provided")
        else:
            feedback.append("Limited reasoning")
        
        return {
            "score": min(score, 10),
            "max_score": 10,
            "feedback": feedback,
            "correct_assignments": correct_count
        }
    
    def evaluate_code_analysis(self, output: str) -> Dict[str, any]:
        """Evaluate code debugging response"""
        score = 0
        feedback = []
        
        # Check for bug identification
        bug_keywords = ['bug', 'issue', 'problem', 'error', 'wrong', 'incorrect']
        has_bug_identification = any(kw in output.lower() for kw in bug_keywords)
        
        if has_bug_identification:
            score += 2
            feedback.append("Bug identified")
        else:
            feedback.append("Bug not explicitly identified")
        
        # Check for understanding the issue (returns duplicates multiple times)
        if 'duplicate' in output.lower() or 'multiple' in output.lower() or 'twice' in output.lower():
            score += 3
            feedback.append("Correctly identifies duplicate issue")
        
        # Check for fix suggestion
        fix_keywords = ['fix', 'solution', 'correct', 'should', 'instead', 'remove']
        has_fix = any(kw in output.lower() for kw in fix_keywords)
        
        if has_fix:
            score += 3
            feedback.append("Fix suggested")
        else:
            feedback.append("No fix suggested")
        
        # Check for code example
        if '```' in output or 'def ' in output:
            score += 2
            feedback.append("Code example provided")
        
        return {
            "score": min(score, 10),
            "max_score": 10,
            "feedback": feedback,
            "identified_bug": has_bug_identification,
            "suggested_fix": has_fix
        }
    
    def evaluate_complex_coding(self, output: str) -> Dict[str, any]:
        """Evaluate LRU cache implementation"""
        score = 0
        feedback = []
        
        # Check for class definition
        if 'class LRUCache' in output or 'class ' in output and 'LRU' in output:
            score += 2
            feedback.append("Class defined")
        
        # Check for required methods
        methods = ['def get', 'def put', 'def __init__']
        methods_found = sum(1 for m in methods if m in output)
        score += methods_found
        
        if methods_found == 3:
            feedback.append("All required methods present")
        else:
            feedback.append(f"{methods_found}/3 methods found")
        
        # Check for data structure usage (OrderedDict or combination)
        ds_keywords = ['OrderedDict', 'dict', 'queue', 'linked', 'hash']
        has_ds = any(kw in output for kw in ds_keywords)
        
        if has_ds:
            score += 2
            feedback.append("Appropriate data structure used")
        
        # Check for O(1) mention or implementation
        if 'O(1)' in output or 'constant' in output.lower():
            score += 2
            feedback.append("Time complexity addressed")
        
        # Check for docstrings/comments
        if '"""' in output or "'''" in output or '#' in output:
            score += 1
            feedback.append("Documentation included")
        
        return {
            "score": min(score, 10),
            "max_score": 10,
            "feedback": feedback,
            "methods_implemented": methods_found
        }
    
    def evaluate_instruction_following(self, output: str) -> Dict[str, any]:
        """Evaluate multi-part instruction following"""
        score = 0
        feedback = []
        
        # Check for exactly 2 sentences
        sentences = [s.strip() for s in output.split('.') if s.strip()]
        if len(sentences) == 2 or (len(sentences) >= 2 and len(sentences) <= 3):
            score += 2
            feedback.append("Approximately 2 sentences for explanation")
        
        # Check for bullet points
        bullets = output.count('•') + output.count('-') + output.count('*')
        if bullets >= 3:
            score += 3
            feedback.append("3+ bullet points included")
        elif bullets >= 1:
            score += 1
            feedback.append("Some bullet points used")
        
        # Check for 1-sentence caution
        caution_patterns = ['caution', 'however', 'but', 'note', 'important', 'beware']
        has_caution = any(p in output.lower() for p in caution_patterns)
        
        if has_caution:
            score += 3
            feedback.append("Caution/qualification included")
        
        # Check format adherence
        format_score = 0
        if 'neural network' in output.lower() or 'neural' in output.lower():
            format_score += 1
        if bullets >= 3:
            format_score += 1
        if has_caution:
            format_score += 1
        
        score += format_score
        
        return {
            "score": min(score, 10),
            "max_score": 10,
            "feedback": feedback,
            "format_adherence": format_score
        }
    
    def evaluate_context_retention(self, output: str) -> Dict[str, any]:
        """Evaluate context retention test"""
        score = 0
        feedback = []
        
        # Check for correct answer (57 books)
        if '57' in output or 'fifty-seven' in output.lower():
            score += 4
            feedback.append("Correct answer (57)")
        elif '50' in output or '60' in output:
            score += 1
            feedback.append("Close but incorrect")
        else:
            feedback.append("Answer unclear/incorrect")
        
        # Check for event references
        events = ['monday', 'wednesday', 'friday', 'damaged', 'returned', 'shipment', 'sold']
        events_found = sum(1 for e in events if e in output.lower())
        score += min(events_found, 4)
        
        if events_found >= 5:
            feedback.append("All events referenced")
        elif events_found >= 3:
            feedback.append("Most events referenced")
        else:
            feedback.append("Few events referenced")
        
        # Check for calculation shown
        calc_markers = ['=', '+', '-', 'start', 'have', 'total', 'left']
        has_calc = sum(1 for m in calc_markers if m in output.lower())
        
        if has_calc >= 2:
            score += 2
            feedback.append("Calculations shown")
        
        return {
            "score": min(score, 10),
            "max_score": 10,
            "feedback": feedback,
            "correct_answer": '57' in output
        }
    
    def evaluate_comparison(self, output: str) -> Dict[str, any]:
        """Evaluate comparative analysis"""
        score = 0
        feedback = []
        
        # Check for all three types mentioned
        types = ['supervised', 'unsupervised', 'reinforcement']
        types_found = sum(1 for t in types if t in output.lower())
        score += types_found * 2
        
        if types_found == 3:
            feedback.append("All three types covered")
        else:
            feedback.append(f"{types_found}/3 types covered")
        
        # Check for characteristics
        if 'characteristic' in output.lower() or 'feature' in output.lower():
            score += 1
            feedback.append("Characteristics discussed")
        
        # Check for applications
        if 'application' in output.lower() or 'example' in output.lower() or 'use' in output.lower():
            score += 1
            feedback.append("Applications provided")
        
        # Check for limitations
        if 'limitation' in output.lower() or 'drawback' in output.lower() or 'disadvantage' in output.lower():
            score += 1
            feedback.append("Limitations discussed")
        
        # Check structure
        structure_markers = ['1.', '2.', '3.', '•', '-', '*']
        has_structure = any(m in output for m in structure_markers)
        
        if has_structure:
            score += 1
            feedback.append("Structured format used")
        
        return {
            "score": min(score, 10),
            "max_score": 10,
            "feedback": feedback,
            "types_covered": types_found
        }
    
    def evaluate_all_outputs(self, benchmark_data: Dict) -> Dict:
        """Evaluate all model outputs"""
        print("Evaluating output quality...\n")
        
        results = {
            "evaluation_date": datetime.now().isoformat(),
            "models": {}
        }
        
        for model_data in benchmark_data.get("models_tested", []):
            model_name = model_data["model"]
            print(f"Evaluating {model_name}...")
            
            model_results = {
                "tests": {},
                "total_score": 0,
                "max_possible": 0
            }
            
            tests = model_data.get("tests", {})
            
            # Evaluate each test
            evaluators = {
                "math_reasoning": self.evaluate_math_reasoning,
                "logic_deduction": self.evaluate_logic_deduction,
                "code_analysis": self.evaluate_code_analysis,
                "complex_coding": self.evaluate_complex_coding,
                "instruction_following": self.evaluate_instruction_following,
                "context_retention": self.evaluate_context_retention,
                "comparison_analysis": self.evaluate_comparison
            }
            
            for test_name, evaluator in evaluators.items():
                if test_name in tests:
                    output = tests[test_name].get("output", "")
                    eval_result = evaluator(output)
                    model_results["tests"][test_name] = eval_result
                    model_results["total_score"] += eval_result["score"]
                    model_results["max_possible"] += eval_result["max_score"]
            
            # Calculate percentage
            if model_results["max_possible"] > 0:
                model_results["quality_percentage"] = round(
                    (model_results["total_score"] / model_results["max_possible"]) * 100, 1
                )
            
            results["models"][model_name] = model_results
            print(f"  Quality Score: {model_results.get('quality_percentage', 0)}%")
        
        return results
    
    def generate_report(self, results: Dict, output_file: str = "quality_evaluation.json"):
        """Generate quality evaluation report"""
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ Quality evaluation saved to: {output_file}")
        
        # Print summary
        print("\n" + "="*60)
        print("QUALITY EVALUATION SUMMARY")
        print("="*60)
        
        # Sort by quality score
        sorted_models = sorted(
            results["models"].items(),
            key=lambda x: x[1].get("quality_percentage", 0),
            reverse=True
        )
        
        for rank, (model, data) in enumerate(sorted_models, 1):
            score = data.get("quality_percentage", 0)
            total = data.get("total_score", 0)
            max_score = data.get("max_possible", 0)
            print(f"\n{rank}. {model}")
            print(f"   Quality Score: {score}% ({total}/{max_score} points)")
            
            # Show best test
            if data.get("tests"):
                best_test = max(data["tests"].items(), key=lambda x: x[1]["score"])
                print(f"   Best Area: {best_test[0].replace('_', ' ').title()} ({best_test[1]['score']}/10)")


def main():
    """Run quality evaluation"""
    print("="*60)
    print("AI MODEL QUALITY EVALUATION")
    print("="*60)
    print("\nThis evaluates the QUALITY of model outputs, not just speed.")
    print("Tests include: correctness, reasoning, and instruction following.\n")
    
    # Load benchmark data
    try:
        with open('accurate_benchmark_20260307_000000.json', 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        print("Accurate benchmark data not found. Using original data...")
        with open('benchmark_results_20260307_183000.json', 'r') as f:
            data = json.load(f)
    
    # Run evaluation
    evaluator = QualityEvaluator()
    results = evaluator.evaluate_all_outputs(data)
    
    # Generate report
    evaluator.generate_report(results)
    
    print("\n" + "="*60)
    print("EVALUATION COMPLETE")
    print("="*60)


if __name__ == "__main__":
    main()
