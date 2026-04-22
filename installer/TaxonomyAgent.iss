[Setup]
AppName=Taxonomy Agent
AppVersion=1.0.0
DefaultDirName={autopf}\Taxonomy Agent
DisableDirPage=no
DefaultGroupName=Taxonomy Agent
OutputDir=output
OutputBaseFilename=TaxonomyAgentSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\dist\Taxonomy Agent.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Taxonomy Agent"; Filename: "{app}\Taxonomy Agent.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Taxonomy Agent"; Filename: "{app}\Taxonomy Agent.exe"; WorkingDir: "{app}"

[Run]
Filename: "{app}\Taxonomy Agent.exe"; Description: "Launch Taxonomy Agent"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent
