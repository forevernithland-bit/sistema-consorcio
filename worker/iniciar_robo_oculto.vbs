' iniciar_robo_oculto.vbs — sobe o robô único SEM janela visível.
' Use este .vbs no atalho de Inicializar (shell:startup) em vez do .bat.
' Nada aparece na tela; os logs continuam em worker\logs\robo.log e console.log.
' Se o processo cair, o watchdog_robo.py (tarefa do Agendador) re-sobe.
Dim sh, aqui
Set sh = CreateObject("WScript.Shell")
aqui = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
sh.CurrentDirectory = aqui
' 0 = janela oculta ; False = não espera terminar
sh.Run "cmd /c """ & aqui & "iniciar_robo.bat""", 0, False
