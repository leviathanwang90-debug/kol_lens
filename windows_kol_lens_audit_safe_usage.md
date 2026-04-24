# Windows PowerShell Safe Audit Script Usage

This is the **safe** version of the audit script for `kol_lens` pre-deployment checks on a Windows server.

## Why a new file is needed

The previous script hit two classes of problems on your machine:

| Problem | Cause |
| --- | --- |
| Parser error near `Python Version` | The original command form was not stable enough for your PowerShell environment. |
| Garbled Chinese text and broken quotes | The file encoding on Windows caused the latter part of the script to be parsed incorrectly. |

The new file `windows_kol_lens_audit_safe.ps1` avoids both issues by using a simpler PowerShell structure and ASCII-only output.

## How to run it

Open **PowerShell as Administrator**, then run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
powershell -ExecutionPolicy Bypass -File C:\Users\Admin\Desktop\windows_kol_lens_audit_safe.ps1 | Tee-Object -FilePath C:\Users\Admin\Desktop\windows_kol_lens_audit_output.txt
```

## What to send back

After it finishes, send me the contents of:

```text
C:\Users\Admin\Desktop\windows_kol_lens_audit_output.txt
```

If you do not want to send the whole file, at least send these sections:

| Required section | Purpose |
| --- | --- |
| `2. CPU and Memory` | Check whether the machine can handle full local deployment |
| `4. Disk Volumes` | Check free storage and data placement |
| `6. Runtime and Tools` | Confirm Python, Node, pnpm, Docker, WSL2 |
| `8. Services` and `9. Port Listening` | Check conflicts with existing services |

## Important note

If this Windows server only has **8GB memory**, it may still be fine for **frontend + backend + PostgreSQL + Redis**, but full local Milvus deployment will remain risky.
