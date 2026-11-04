' Inicia o Agente Vigia STI totalmente em segundo plano (sem janela preta de prompt)
Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
strCurrentDir = FSO.GetParentFolderName(WScript.ScriptFullName)

strPython = "python"
If FSO.FileExists(strCurrentDir & "\.venv\Scripts\python.exe") Then
    strPython = """" & strCurrentDir & "\.venv\Scripts\python.exe"""
End If

strCmd = strPython & " """ & strCurrentDir & "\sync_agent.py"" --loop 30"
WshShell.CurrentDirectory = strCurrentDir
' 0 = Oculta a janela completamente
WshShell.Run strCmd, 0, False
