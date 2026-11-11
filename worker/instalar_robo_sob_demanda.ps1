# instalar_robo_sob_demanda.ps1 — roda UMA vez, no NOTEBOOK SERVIDOR (o que hospeda o robô).
# Cria a tarefa "Robo Consorbens - Watchdog" (a cada 1 min, sem janela, Python 3.14) que liga o robô
# quando alguém usa o CRM e desliga 60 min depois. Também tira o robô do início automático do Windows
# (quem liga agora é o watchdog). Pré-requisito: migração 33 rodada no Supabase.
#
# Uso (PowerShell, na pasta worker):  powershell -ExecutionPolicy Bypass -File .\instalar_robo_sob_demanda.ps1
# Para voltar ao "sempre ligado": [sob_demanda] ativo = false em robo_config.toml (a tarefa continua vigiando).

$ErrorActionPreference = "Stop"
$aqui = Split-Path -Parent $MyInvocation.MyCommand.Path
$nome = "Robo Consorbens - Watchdog"

# pythonw do 3.14 = sem janela piscando a cada minuto
$pyw = (& py -V:3.14 -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))").Trim()
if (-not (Test-Path $pyw)) { throw "pythonw 3.14 não encontrado ($pyw)" }

$acao = New-ScheduledTaskAction -Execute $pyw -Argument "`"$aqui\watchdog_robo.py`"" -WorkingDirectory $aqui
$gatilho = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$conf = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
Unregister-ScheduledTask -TaskName $nome -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $nome -Action $acao -Trigger $gatilho -Settings $conf `
    -Description "Liga o robô Consorbens quando alguém usa o CRM e desliga 60 min depois." | Out-Null
Write-Host "Tarefa '$nome' criada (a cada 1 min)."

# tira o robô do início automático (o watchdog liga quando precisa)
$lnk = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\Robo Consorbens.lnk"
if (Test-Path $lnk) { Move-Item $lnk "$lnk.desativado" -Force; Write-Host "Atalho de início automático desativado." }

Write-Host "`nSimulação da decisão agora:"
& py -V:3.14 "$aqui\watchdog_robo.py" --simular
