import re
data = open('templates/company_dashboard.html').read()
tags = re.findall(r'\{%\s*(if|else|endif|for|empty|endfor)\b[^%]*%\}', data)
stack = []
for idx, m in enumerate(re.finditer(r'\{%\s*(if|else|endif|for|empty|endfor)\b([^%]*)%\}', data)):
    tag = m.group(1)
    line = data[:m.start()].count('\n') + 1
    print(f"Line {line}: {m.group(0)}")
