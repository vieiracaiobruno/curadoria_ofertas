#!/bin/bash

# Script para configurar o cron job do sistema de curadoria de ofertas

PROJECT_DIR="/home/ubuntu/curadoria_ofertas"
PYTHON_PATH="$PROJECT_DIR/venv/bin/python"
SCRIPT_PATH="$PROJECT_DIR/run_pipeline.py"

# Cria o cron job para executar a cada 2 horas
CRON_JOB="0 */2 * * * cd $PROJECT_DIR && $PYTHON_PATH $SCRIPT_PATH >> $PROJECT_DIR/cron.log 2>&1"

# Adiciona o cron job se não existir
(crontab -l 2>/dev/null | grep -v "$SCRIPT_PATH"; echo "$CRON_JOB") | crontab -

echo "Cron job configurado para executar a cada 2 horas:"
echo "$CRON_JOB"
echo ""
echo "Para verificar os cron jobs ativos, execute: crontab -l"
echo "Para ver os logs do cron, execute: tail -f $PROJECT_DIR/cron.log"

