"""Local, rule-based study coach. Python standard library only."""
import argparse
from contextlib import contextmanager
from datetime import date, datetime
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
LABEL = 'local.study-coach'


def validate_date(value):
    try:
        parsed = date.fromisoformat(value)
    except ValueError as e:
        raise ValueError('日期格式必须是 YYYY-MM-DD') from e
    if parsed.isoformat() != value:
        raise ValueError('日期格式必须是 YYYY-MM-DD')
    return value


def atomic_json(filename, data):
    path = Path(filename)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name + '.')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def locked():
    # The menu holds the lock; scheduled checks retry next minute.
    import fcntl
    with open(ROOT / '.coach.lock', 'a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            raise ValueError('教练正在运行，请先关闭另一个交互窗口') from e
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


class Coach:
    def __init__(self, todo_list):
        self.todo_list = todo_list
        self.filename = Path(todo_list.filename).with_name('coach.json')
        self.state = {'days': {}, 'notified': []}
        if self.filename.exists():
            self.state = json.loads(self.filename.read_text(encoding='utf-8'))
            if not isinstance(self.state, dict) or not isinstance(self.state.get('days'), dict) or not isinstance(self.state.get('notified'), list):
                raise ValueError('coach.json 格式错误，未覆盖原文件')

    def save(self):
        atomic_json(self.filename, self.state)

    def plan(self, indices=None, day=None):
        day = validate_date(day or date.today().isoformat())
        if indices is None:
            indices = sorted(
                (i for i, t in enumerate(self.todo_list.todos) if not t['completed']),
                key=lambda i: (
                    not (self.todo_list.todos[i]['due'] and self.todo_list.todos[i]['due'] <= day),
                    self.todo_list.todos[i]['priority'],
                    self.todo_list.todos[i]['due'] or '9999-12-31', i
                )
            )[:3]
        if not indices or len(set(indices)) != len(indices) or any(
            i < 0 or i >= len(self.todo_list.todos) or self.todo_list.todos[i]['completed'] for i in indices
        ):
            raise ValueError('请选择不同的未完成任务；没有任务时请先添加')
        record = self.state['days'].setdefault(day, {})
        if 'plan' in record:
            raise ValueError('当天计划已确定，保留原计划用于真实复盘；明天可重新选任务')
        # Save stable IDs plus snapshots, so deletions cannot erase the denominator.
        record['plan'] = [{'id': self.todo_list.todos[i]['id'], 'task': self.todo_list.todos[i]['task']} for i in indices]
        self.todo_list.save_todos()
        self.save()

    def summary(self, day=None):
        day = validate_date(day or date.today().isoformat())
        record = self.state['days'].get(day, {})
        plan = record.get('plan', [])
        current = {t['id']: t for t in self.todo_list.todos}
        done = 0
        lines = [f'{day} 每日计划']
        for item in plan:
            task = current.get(item['id'])
            stamp = (task or item).get('completed_at')
            finished = bool(stamp and stamp[:10] <= day)
            done += finished
            status = '完成' if finished else ('已删除/未完成' if task is None else '未完成')
            lines.append(f"[{status}] {item['task']}")
        lines.append(f'计划完成: {done}/{len(plan)} ({done / len(plan):.0%})' if plan else '尚未制定计划')
        completed_today = sum(bool(t.get('completed_at') and t['completed_at'][:10] == day) for t in self.todo_list.todos)
        lines.append(f'当前任务中当天完成: {completed_today} 项')
        overdue = [t['task'] for t in self.todo_list.todos if not t['completed'] and t['due'] and t['due'] < day]
        if overdue:
            lines.append('逾期: ' + '；'.join(overdue))
        if record.get('review'):
            lines.append('复盘: ' + record['review']['note'])
            lines.append('下一步: ' + record['review']['next_step'])
        lines.append('教练建议: 先做一个 25 分钟小步骤，留下可检查的成果。')
        return '\n'.join(lines)

    def review(self, note, next_step, day=None):
        if not note.strip() or not next_step.strip():
            raise ValueError('请填写成果/卡点和下一步')
        day = validate_date(day or date.today().isoformat())
        self.state['days'].setdefault(day, {})['review'] = {
            'note': note, 'next_step': next_step,
            'saved_at': datetime.now().isoformat(timespec='seconds')
        }
        self.save()

    def archive_deleted(self, task):
        for record in self.state['days'].values():
            for item in record.get('plan', []):
                if item['id'] == task['id']:
                    item['completed_at'] = task.get('completed_at')
        self.save()

    def remind(self, now=None, dry_run=False):
        now = now or datetime.now()
        day = now.date().isoformat()
        record = self.state['days'].get(day, {})
        messages = []
        if now.hour >= 9 and 'plan' not in record:
            messages.append(('plan', '先确定今天最多三项科研/学习重点。'))
        urgent = [t['task'] for t in self.todo_list.todos if not t['completed'] and t['due'] and t['due'] <= day]
        if now.hour >= 10 and urgent:
            messages.append(('due', '到期/逾期任务: ' + '；'.join(urgent)))
        if now.hour >= 21 and 'review' not in record:
            messages.append(('review', '记录今天的成果、卡点和明天的最小下一步。'))
        for kind, message in messages:
            key = day + ':' + kind
            if key in self.state['notified']:
                continue
            if dry_run:
                print(message)
                continue
            if sys.platform != 'darwin':
                raise ValueError('系统通知仅支持 macOS；其他平台可使用 --dry-run')
            # argv transport avoids interpolating task text into AppleScript code.
            script = 'on run argv\n display notification (item 1 of argv) with title "科研/学习教练"\nend run'
            subprocess.run(['/usr/bin/osascript', '-e', script, message[:500]], check=True, timeout=15)
            self.state['notified'].append(key)
            self.state['notified'] = [k for k in self.state['notified'] if k.startswith(day)]
            self.save()


def launch_agent(install):
    if sys.platform != 'darwin':
        raise ValueError('LaunchAgent 仅支持 macOS')
    path = Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')
    domain = f'gui/{os.getuid()}'
    if install:
        if path.exists():
            raise ValueError('提醒已安装；请先运行 --uninstall-reminders 再重新安装')
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            'Label': LABEL,
            'ProgramArguments': [sys.executable, str(ROOT / 'todo_app.py'), '--remind'],
            'StartInterval': 60,
            'RunAtLoad': True,
            'WorkingDirectory': str(ROOT),
            'StandardOutPath': str(ROOT / 'reminders.log'),
            'StandardErrorPath': str(ROOT / 'reminders.log'),
        }
        with path.open('wb') as stream:
            plistlib.dump(payload, stream)
        try:
            subprocess.run(['/bin/launchctl', 'bootstrap', domain, str(path)], check=True)
        except subprocess.CalledProcessError:
            path.unlink()
            raise
        print('已安装本地提醒：09点计划、10点到期、21点复盘，每类每天最多一次')
    else:
        if not path.exists():
            print('未安装提醒')
            return
        result = subprocess.run(['/bin/launchctl', 'bootout', domain + '/' + LABEL], capture_output=True, text=True)
        if result.returncode:
            # Missing service is harmless; other launchctl failures leave the plist intact.
            check = subprocess.run(['/bin/launchctl', 'print', domain + '/' + LABEL], capture_output=True)
            if check.returncode == 0:
                raise ValueError('停止提醒失败，保留配置: ' + result.stderr)
        path.unlink()
        print('已卸载本地提醒')


def entrypoint(menu):
    parser = argparse.ArgumentParser(description='科研/学习教练（本地规则版）')
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--remind', action='store_true')
    actions.add_argument('--summary', action='store_true')
    actions.add_argument('--install-reminders', action='store_true')
    actions.add_argument('--uninstall-reminders', action='store_true')
    parser.add_argument('--dry-run', action='store_true', help='仅打印提醒，不发送、不记录')
    parser.add_argument('--date', help='--summary 查看指定日期 YYYY-MM-DD')
    args = parser.parse_args()
    if args.dry_run and not args.remind or args.date and not args.summary:
        parser.error('--dry-run 配合 --remind；--date 配合 --summary')
    try:
        if args.install_reminders or args.uninstall_reminders:
            launch_agent(args.install_reminders)
            return
        with locked():
            if args.remind or args.summary:
                from todo_app import TodoList
                todos = TodoList()
                coach = Coach(todos)
                if args.summary:
                    print(coach.summary(args.date))
                else:
                    coach.remind(dry_run=args.dry_run)
            else:
                menu()
    except (ValueError, OSError, subprocess.SubprocessError) as e:
        print(f'错误: {e}', file=sys.stderr)
        sys.exit(1)
    except (EOFError, KeyboardInterrupt):
        print('\n再见！')
