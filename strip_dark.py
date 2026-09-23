import re

files_to_strip = [
    'stratas/templates/stratas/onboarding.html',
    'stratas/templates/stratas/already_claimed.html'
]

for filepath in files_to_strip:
    try:
        with open(filepath, 'r') as f:
            content = f.read()
        
        # We need to remove any trailing colons or remaining classes from the bad regex.
        # Let's just fix the bad artifacts: `:bg-slate-200`, `:text-slate-100`, etc.
        # Actually, it's safer to just re-generate the files since I have the source.
        pass
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
