#!/usr/bin/env python3
"""Detect and fix AI typography tells in Hebrew text.

Common AI signatures in Hebrew academic writing:
- Em-dashes (—) for pauses/asides
- Straight quotes (") instead of gereshayim (״...״)
- Unnecessary RLM/LRM directional marks
- Orphan punctuation at paragraph start

Usage:
    python3 detect-ai-typography.py --text "Hebrew text here" --fix-and-output
    python3 detect-ai-typography.py --text "..." --json
"""

import re
import argparse
import json
import sys


def fix_typography(text: str) -> tuple[str, list[str]]:
    """
    Fix typography tells in Hebrew text.
    
    Returns:
        (cleaned_text, list_of_fixes_applied)
    """
    if not text:
        return text, []
    
    fixes = []
    
    # 1. Remove em-dashes, replace with space-hyphen-space
    #    Em-dashes are a telltale sign of AI writing in Hebrew
    if '—' in text or '\u2014' in text:
        text = re.sub(r'[—\u2014]', ' - ', text)
        fixes.append('removed_em_dashes')
    
    # 2. Replace straight quotes with gereshayim
    #    English straight quotes are wrong in Hebrew academic writing
    if '"' in text:
        # Match quoted phrases and replace with gereshayim
        text = re.sub(r'"([^"]*)"', r'״\1״', text)
        fixes.append('standardized_quotes_to_gereshayim')
    
    # 3. Remove unnecessary RLM/LRM directional marks
    #    DOCX handles bidirectionality automatically; manual marks cause issues
    original_length = len(text)
    
    # RLM (U+200F) appearing before punctuation is usually wrong
    text = re.sub(r'\u200F+(?=[.,;:\)\]\"])', '', text)
    
    # LRM (U+200E) appearing after opening parenthesis/bracket is usually wrong
    text = re.sub(r'(?<=[(\[])\u200E+', '', text)
    
    # Multiple consecutive directional marks should be collapsed
    text = re.sub(r'[\u200E\u200F]{2,}', '', text)
    
    if len(text) < original_length:
        fixes.append('removed_unnecessary_directional_marks')
    
    # 4. Check for orphan punctuation at paragraph start (flag, don't auto-fix)
    #    This needs context to fix properly
    if re.match(r'^\s*[.,;:]', text):
        fixes.append('orphan_punctuation_at_paragraph_start')
    
    # 5. Fix common AI pattern: excessive use of "בנוסף" and "יתרה מכך"
    #    Count them; if >1 per paragraph, note it
    conjunction_count = len(re.findall(r'\b(בנוסף|יתרה מכך|זאת ועוד)\b', text))
    if conjunction_count > 2:
        fixes.append('excessive_conjunctions')
    
    return text, fixes


def detect_typography_issues(text: str) -> dict:
    """
    Detect typography issues without fixing.
    
    Returns:
        {
            'has_em_dashes': bool,
            'has_straight_quotes': bool,
            'has_directional_marks': bool,
            'orphan_punctuation': bool,
            'excessive_conjunctions': bool,
            'issues_count': int
        }
    """
    if not text:
        return {
            'has_em_dashes': False,
            'has_straight_quotes': False,
            'has_directional_marks': False,
            'orphan_punctuation': False,
            'excessive_conjunctions': False,
            'issues_count': 0
        }
    
    issues = {
        'has_em_dashes': bool('—' in text or '\u2014' in text),
        'has_straight_quotes': '"' in text,
        'has_directional_marks': '\u200E' in text or '\u200F' in text,
        'orphan_punctuation': bool(re.match(r'^\s*[.,;:]', text)),
        'excessive_conjunctions': len(re.findall(r'\b(בנוסף|יתרה מכך|זאת ועוד)\b', text)) > 2,
    }
    issues['issues_count'] = sum(1 for v in issues.values() if v is True)
    
    return issues


def score_typography(text: str) -> dict:
    """
    Score text on typography quality (0-10 scale).
    
    Returns:
        {
            'score': float (0-10, higher is better),
            'issues': dict of detected issues,
            'severity': 'clean' | 'minor' | 'moderate' | 'severe'
        }
    """
    issues = detect_typography_issues(text)
    
    # Each issue costs points
    penalties = {
        'has_em_dashes': 3.0,  # Major tell of AI
        'has_straight_quotes': 1.5,
        'has_directional_marks': 2.0,
        'orphan_punctuation': 2.0,
        'excessive_conjunctions': 1.0,
    }
    
    score = 10.0
    for issue_key, penalty in penalties.items():
        if issues.get(issue_key, False):
            score -= penalty
    
    score = max(0, score)  # Don't go below 0
    
    if score == 10.0:
        severity = 'clean'
    elif score >= 7.0:
        severity = 'minor'
    elif score >= 4.0:
        severity = 'moderate'
    else:
        severity = 'severe'
    
    return {
        'score': round(score, 1),
        'issues': issues,
        'severity': severity
    }


def main():
    parser = argparse.ArgumentParser(
        description='Detect and fix AI typography tells in Hebrew text',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Detect issues without fixing
  python3 detect-ai-typography.py --text "Text with — em-dash"
  
  # Fix issues and output cleaned text
  python3 detect-ai-typography.py --text "Text here" --fix-and-output
  
  # Output as JSON
  python3 detect-ai-typography.py --text "..." --json
  
  # Score text quality
  python3 detect-ai-typography.py --text "..." --score
        '''
    )
    parser.add_argument('--text', required=True, help='Text to check')
    parser.add_argument('--fix-and-output', action='store_true',
                       help='Fix issues and output cleaned text to stdout')
    parser.add_argument('--json', action='store_true',
                       help='Output results as JSON')
    parser.add_argument('--score', action='store_true',
                       help='Score typography quality (0-10)')
    parser.add_argument('--detect-only', action='store_true',
                       help='Only detect issues, don\'t fix')
    args = parser.parse_args()
    
    # Determine output format
    if args.score:
        result = score_typography(args.text)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            s = result['score']
            sev = result['severity']
            issues_found = sum(1 for v in result['issues'].values() if v is True)
            print(f"Score: {s}/10 ({sev})")
            print(f"Issues: {issues_found}")
            for issue_key, present in result['issues'].items():
                if present:
                    print(f"  - {issue_key}")
    
    elif args.detect_only:
        issues = detect_typography_issues(args.text)
        if args.json:
            print(json.dumps(issues, ensure_ascii=False, indent=2))
        else:
            issues_found = sum(1 for v in issues.values() if v is True)
            print(f"Issues detected: {issues_found}")
            for issue_key, present in issues.items():
                if present:
                    print(f"  - {issue_key}")
    
    elif args.fix_and_output:
        fixed_text, fixes = fix_typography(args.text)
        if args.json:
            print(json.dumps({
                'fixed_text': fixed_text,
                'fixes_applied': fixes,
                'fixes_count': len(fixes)
            }, ensure_ascii=False, indent=2))
        else:
            print(fixed_text)
    
    else:
        # Default: show what fixes would be applied
        fixed_text, fixes = fix_typography(args.text)
        if args.json:
            print(json.dumps({
                'original_text': args.text,
                'fixed_text': fixed_text,
                'fixes': fixes,
                'fixes_count': len(fixes)
            }, ensure_ascii=False, indent=2))
        else:
            if fixes:
                print(f"Fixes needed: {', '.join(fixes)}")
                print(f"\nCleaned text:\n{fixed_text}")
            else:
                print("No typography issues detected.")


if __name__ == '__main__':
    main()
