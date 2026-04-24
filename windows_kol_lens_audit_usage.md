# Windows 本地服务器一键盘点使用说明

**作者：Manus AI**  
**日期：2026-04-21**

你要执行的核心文件是附件里的 `windows_kol_lens_audit.ps1`。这个脚本会一次性盘点：**Windows 版本、CPU、内存、磁盘、页面文件、IP、Python / Node / pnpm / Docker、服务状态、端口占用、以及与 `kol_lens` 相关的 PostgreSQL / Redis / Milvus / Nginx 运行条件**。

## 一、如何执行

建议你用 **PowerShell（管理员）** 执行。把脚本复制到你的 Windows 服务器上，例如放到桌面，然后运行下面两条命令：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
powershell -ExecutionPolicy Bypass -File .\windows_kol_lens_audit.ps1
```

如果你不想改当前目录，也可以直接用绝对路径：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
powershell -ExecutionPolicy Bypass -File C:\path\to\windows_kol_lens_audit.ps1
```

## 二、建议怎样保存输出

为了避免控制台滚动太快，建议你把输出直接重定向到一个文本文件：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
powershell -ExecutionPolicy Bypass -File .\windows_kol_lens_audit.ps1 | Tee-Object -FilePath .\windows_kol_lens_audit_output.txt
```

这样执行后，当前目录会生成一个 `windows_kol_lens_audit_output.txt`，你把这个文件内容发给我即可。

## 三、如果 PowerShell 阻止执行怎么办

如果系统提示脚本执行受限，优先用下面这个方式，不要全局放开：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

这只对当前 PowerShell 窗口生效，关掉窗口后不会长期修改系统策略。

## 四、你至少要回传哪些结果

如果你不想贴完整输出，至少把下面四段贴回来：

| 必回传部分 | 作用 |
| --- | --- |
| `2. CPU 与内存` | 判断能否承载 Milvus 与完整链路 |
| `4. 磁盘与卷` | 判断系统盘 / 数据盘是否足够 |
| `6. 常用运行时与工具` | 判断 Python、Node、pnpm、Docker 是否齐全 |
| `8. 服务检测` 与 `9. 端口占用` | 判断是否与现有服务冲突 |

## 五、我会如何帮你解读结果

你把输出贴给我后，我会继续帮你判断三件事：

1. **这台 Windows 服务器是否适合完整部署 `kol_lens`；**
2. **如果不适合完整部署，哪些组件应该改为远端；**
3. **如果适合，我会进一步给你部署顺序。**

## 六、额外提醒

> 对 `kol_lens` 来说，真正要重点关注的是：**内存、Docker / WSL2、以及 `19530` 端口和 Milvus 依赖链**。如果机器只有 `8GB` 内存，那么即便 Windows 本地能装，也不代表适合完整承载。
