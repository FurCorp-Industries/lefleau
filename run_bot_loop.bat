@echo off
REM =============================================================
REM run_bot_loop.bat
REM ---------------------------------------------------------------
REM Relance automatiquement le bot s'il plante ou s'arrête, sans que
REM tu aies besoin d'intervenir. Utile quand tu es loin de ton PC
REM (le bot redémarre tout seul 5 secondes après un crash).
REM
REM Utilisation : double-clique sur ce fichier au lieu de faire
REM "python bot.py" directement. Laisse la fenêtre ouverte.
REM Pour arrêter définitivement : ferme la fenêtre (ou Ctrl+C, puis
REM tape "n" si ça demande confirmation d'arrêt du script batch).
REM =============================================================

cd /d "%~dp0"

:loop
echo.
echo ============================================
echo   Demarrage du bot One Piece - %DATE% %TIME%
echo ============================================
python bot.py

echo.
echo Le bot s'est arrete ou a plante. Redemarrage dans 5 secondes...
echo (Ferme cette fenetre pour arreter completement le bot)
timeout /t 5 /nobreak > nul
goto loop
