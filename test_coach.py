import io
import json
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from todo_app import TodoList
from coach import Coach


class CoachTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'todos.json'

    def test_legacy_migration_and_completion_timestamp(self):
        self.path.write_text('[{"task":"旧任务","completed":false}]')
        todos = TodoList(str(self.path))
        todos.save_todos()
        stable_id = todos.todos[0]['id']
        todos = TodoList(str(self.path))
        self.assertEqual(todos.todos[0]['id'], stable_id)
        todos.complete_todo(0)
        stamp = todos.todos[0]['completed_at']
        todos.complete_todo(0)
        self.assertEqual(todos.todos[0]['completed_at'], stamp)

    def test_plan_ranking_and_deleted_history(self):
        todos = TodoList(str(self.path))
        todos.add_todo('论文', 1, '2026-10-05')
        todos.add_todo('到期实验', 3, '2026-09-30')
        todos.add_todo('推导', 1)
        todos.add_todo('杂事', 3)
        coach = Coach(todos)
        coach.plan(day='2026-09-30')
        self.assertEqual([t['task'] for t in coach.state['days']['2026-09-30']['plan']], ['到期实验', '论文', '推导'])
        todos.todos[1].update(completed=True, completed_at='2026-09-30T12:00:00')
        todos.save_todos()
        todos.delete_todo(1)
        coach = Coach(todos)
        self.assertIn('1/3', coach.summary('2026-09-30'))
        with self.assertRaises(ValueError):
            coach.plan([0], '2026-09-30')
        coach.review('推导完成', '检查边界条件', '2026-09-30')
        self.assertIn('检查边界条件', Coach(todos).summary('2026-09-30'))

    def test_late_completion_not_counted_for_previous_day(self):
        todos = TodoList(str(self.path))
        todos.add_todo('计算')
        coach = Coach(todos)
        coach.plan(day='2026-09-30')
        todos.todos[0]['completed_at'] = '2026-10-01T10:00:00'
        self.assertIn('0/1', coach.summary('2026-09-30'))

    def test_invalid_data_not_overwritten(self):
        self.path.write_text('{broken')
        with self.assertRaises(ValueError):
            TodoList(str(self.path))
        self.assertEqual(self.path.read_text(), '{broken')
        todos = TodoList(str(Path(self.tmp.name) / 'new.json'))
        for due in ['2026-02-30', '20260930']:
            with self.assertRaises(ValueError):
                todos.add_todo('测试', due=due)
        with self.assertRaises(ValueError):
            todos.add_todo('测试', priority=0)

    def test_reminder_dedup_dry_run_and_failure_retry(self):
        todos = TodoList(str(self.path))
        todos.add_todo('含 " 引号的任务', due='2026-09-30')
        coach = Coach(todos)
        now = datetime(2026, 9, 30, 22)
        with redirect_stdout(io.StringIO()):
            coach.remind(now, dry_run=True)
        self.assertEqual(coach.state['notified'], [])
        with patch('coach.sys.platform', 'darwin'), patch('coach.subprocess.run') as run:
            coach.remind(now)
            coach.remind(now)
            self.assertEqual(run.call_count, 3)
            self.assertIn('引号', run.call_args_list[1].args[0][-1])
        coach.state['notified'] = []
        with patch('coach.sys.platform', 'darwin'), patch('coach.subprocess.run', side_effect=OSError('失败')):
            with self.assertRaises(OSError):
                coach.remind(now)
        self.assertEqual(coach.state['notified'], [])


if __name__ == '__main__':
    unittest.main()
