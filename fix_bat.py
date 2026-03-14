import os
filepath = r'c:\Users\LU\Desktop\Kaggle_remote_zrok\start_client.bat'
with open(filepath, 'rb') as f:
    text = f.read().decode('utf-8', errors='ignore')
text = text.replace('\u2500', '-')
lines = text.splitlines()
with open(filepath, 'wb') as f:
    f.write(('\r\n'.join(lines) + '\r\n').encode('ascii', errors='ignore'))
print("Fixed start_client.bat")
