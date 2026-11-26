#!/bin/bash
# Inside the nested KWin: scenario.sh WORK click|enter|control. A running browser, a program in front
# of it, a click on a link there, a choice in our window. WORK/result tells whether the browser came up.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
work=$1 scenario=$2
export PATH="$work/bin:$PATH"
rm -f "$work/fifo" "$work/result"
mkfifo "$work/fifo"
python3 "$here/browser.py" "$work/fifo" "$work/result" &
sleep 1.2
python3 "$here/messenger.py" &
sleep 1.2
python3 "$here/inject.py" 1440 900
case $scenario in
control) ;;
click) sleep 2 && python3 "$here/inject.py" 1347 926 ;;
enter) sleep 2 && python3 "$here/inject.py" key 28 ;;
esac
sleep 2.5
kill %1 %2
