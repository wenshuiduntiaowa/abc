"""
简单的待办事项管理应用
"""
import json
import os
from datetime import datetime
from pathlib import Path
import uuid

class TodoList:
    def __init__(self, filename=None):
        filename = filename or str(Path(__file__).resolve().with_name('todos.json'))
        self.filename = filename
        self.todos = []
        self.load_todos()

    def load_todos(self):
        """从文件加载待办事项"""
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r', encoding='utf-8') as f:
                    self.todos = json.load(f)
                if not isinstance(self.todos, list) or any(
                    not isinstance(t, dict) or not isinstance(t.get('task'), str)
                    or not isinstance(t.get('completed', False), bool)
                    for t in self.todos
                ):
                    raise ValueError("任务文件必须是包含 task/completed 的列表")
            except (json.JSONDecodeError, IOError) as e:
                raise ValueError(f"加载失败，未覆盖原文件: {e}") from e
        else:
            self.todos = []
        for todo in self.todos:
            todo.setdefault('id', uuid.uuid4().hex)
            todo.setdefault('priority', 2)
            todo.setdefault('due', None)
            todo.setdefault('completed_at', None)
            from coach import validate_date
            if todo['priority'] not in (1, 2, 3):
                raise ValueError("任务优先级损坏，未覆盖原文件")
            if todo['due']:
                validate_date(todo['due'])
            if todo['completed_at']:
                datetime.fromisoformat(todo['completed_at'])

    def save_todos(self):
        """保存待办事项到文件"""
        from coach import atomic_json
        atomic_json(self.filename, self.todos)

    def add_todo(self, task, priority=2, due=None):
        """添加新的待办事项"""
        from coach import validate_date
        if not task.strip() or priority not in (1, 2, 3):
            raise ValueError("任务不能为空；优先级为 1、2、3")
        if due:
            validate_date(due)
        todo = {
            'id': uuid.uuid4().hex,
            'priority': priority,
            'due': due,
            'completed_at': None,
            'task': task,
            'completed': False
        }
        self.todos.append(todo)
        self.save_todos()

    def list_todos(self):
        """列出所有待办事项"""
        if not self.todos:
            print("没有待办事项")
            return

        print("\n=== 待办事项列表 ===")
        for i, todo in enumerate(self.todos, 1):
            status = "✓" if todo.get('completed', False) else " "
            print(f"{i}. [{status}] P{todo['priority']} {todo['task']} 截止: {todo['due'] or '无'}")
        print()

    def complete_todo(self, index):
        """标记待办事项为完成"""
        if 0 <= index < len(self.todos):
            if self.todos[index]['completed']:
                print("该任务已经完成")
                return
            self.todos[index]['completed'] = True
            self.todos[index]['completed_at'] = datetime.now().isoformat(timespec='seconds')
            self.save_todos()
            print("已标记为完成！")
        else:
            print("无效的索引")

    def delete_todo(self, index):
        """删除待办事项"""
        if 0 <= index < len(self.todos):
            from coach import Coach
            Coach(self).archive_deleted(self.todos[index])
            deleted = self.todos.pop(index)
            self.save_todos()
            print(f"已删除: {deleted['task']}")
        else:
            print("无效的索引")


def main():
    """主函数"""
    from coach import Coach
    todo_list = TodoList()
    todo_list.save_todos()
    coach = Coach(todo_list)

    while True:
        print("\n=== 待办事项管理 ===")
        print("1. 添加待办事项")
        print("2. 查看待办事项")
        print("3. 完成待办事项")
        print("4. 删除待办事项")
        print("5. 退出")
        print("6. 每日计划（留空自动选择最多 3 项）")
        print("7. 今日计划与完成情况")
        print("8. 今日复盘")
        print("9. 修改优先级/截止日期")

        choice = input("\n请选择操作 (1-9): ").strip()

        if choice == '1':
            task = input("请输入待办事项: ").strip()
            if task:
                try:
                    priority = int(input("优先级 1最高/2普通/3低 [2]: ") or '2')
                    due = input("截止日期 YYYY-MM-DD（留空无）: ").strip() or None
                    todo_list.add_todo(task, priority, due)
                    print("添加成功！")
                except ValueError as e:
                    print(e)

        elif choice == '2':
            todo_list.list_todos()

        elif choice == '3':
            todo_list.list_todos()
            try:
                index = int(input("请输入要完成的事项编号: ")) - 1
                todo_list.complete_todo(index)
            except (ValueError, IndexError):
                print("无效的编号")

        elif choice == '4':
            todo_list.list_todos()
            try:
                index = int(input("请输入要删除的事项编号: ")) - 1
                todo_list.delete_todo(index)
                coach = Coach(todo_list)
            except (ValueError, IndexError):
                print("无效的编号")

        elif choice == '5':
            print("再见！")
            break
        elif choice == '6':
            todo_list.list_todos()
            try:
                raw = input("任务编号，逗号分隔（留空自动选择）: ").strip()
                coach.plan([int(x) - 1 for x in raw.split(',')] if raw else None)
                print(coach.summary())
            except ValueError as e:
                print(e)
        elif choice == '7':
            print(coach.summary())
        elif choice == '8':
            print(coach.summary())
            try:
                coach.review(input("今天的成果/卡点: ").strip(), input("明天的最小下一步: ").strip())
                print("复盘已保存")
            except ValueError as e:
                print(e)
        elif choice == '9':
            todo_list.list_todos()
            try:
                index = int(input("任务编号: ")) - 1
                if not 0 <= index < len(todo_list.todos):
                    raise ValueError("无效的编号")
                priority = int(input("优先级 1/2/3: "))
                due = input("截止日期 YYYY-MM-DD（留空清除）: ").strip() or None
                from coach import validate_date
                if priority not in (1, 2, 3):
                    raise ValueError("优先级为 1、2、3")
                if due:
                    validate_date(due)
                todo_list.todos[index].update(priority=priority, due=due)
                todo_list.save_todos()
            except ValueError as e:
                print(e)

        else:
            print("无效的选择，请重试")


if __name__ == '__main__':
    from coach import entrypoint
    entrypoint(main)
