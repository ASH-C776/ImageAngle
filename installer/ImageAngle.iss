; ImageAngle 安装包（Inno Setup 6）
;
; 由 scripts/build.py 调用：
;   ISCC.exe /DAppVer=1.0.4 /DStageDir=<dist>\ImageAngle-1.0.4 /O<dist> installer\ImageAngle.iss
;
; 设计取舍：
;   - PrivilegesRequired=lowest → 装到 %LOCALAPPDATA%\Programs，不需要管理员、不弹 UAC。
;     诊所电脑常常没有管理员权限，这一条决定了 IT 能不能直接部署。
;   - 用户数据在 %APPDATA%\ImageAngle（不在安装目录），所以覆盖安装、卸载都不会丢测量记录。
;     卸载时也不主动删它 —— 删数据必须是用户自己明确做的事。

#ifndef AppVer
  #define AppVer "0.0.0"
#endif
#ifndef StageDir
  #define StageDir "..\dist\ImageAngle"
#endif

#define AppName "ImageAngle"
#define AppExe "ImageAngle.exe"
#define AppPublisher "ImageAngle"
#define AppId "{{9C1E4F62-7B3A-4D58-A2E1-5C6F0B8D4731}"

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#AppVer}
AppVerName={#AppName} {#AppVer}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputBaseFilename=ImageAngle-{#AppVer}-安装包
SetupIconFile=..\resources\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
; 覆盖安装时沿用上次的目录，别把程序装成两份
UsePreviousAppDir=yes
; 显式写版本资源：不写的话 Inno 只填数值版本，FileVersion/ProductVersion 字符串是空的，
; 资源管理器「详细信息」里那两栏会显示空白，某些脚本读出来还会带脏字符
VersionInfoVersion={#AppVer}.0
VersionInfoProductVersion={#AppVer}.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} 安装程序
VersionInfoProductName={#AppName}
VersionInfoCopyright=MIT License

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："; Flags: unchecked

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\卸载 {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "立即启动 {#AppName}"; Flags: nowait postinstall skipifsilent

[Messages]
; 装完提示里点明数据位置，省得用户以为卸载会连记录一起删
chinesesimplified.FinishedLabel=安装已完成，现在可以启动 {#AppName}。%n%n测量记录保存在：%n%APPDATA%\ImageAngle%n卸载不会删除该目录。
