"""
简单的待办事项管理应用
"""
import json
import os

class TodoList:
    def __init__(self, filename='todos.json'):
        self.filename = filename
        self.todos = []
        self.load_todos()

    def load_todos(self):
        """从文件加载待办事项"""
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r', encoding='utf-8') as f:
                    self.todos = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"加载待办事项失败: {e}")
                self.todos = []
        else:
            self.todos = []

    def save_todos(self):
        """保存待办事项到文件"""
        try:
            with open(self.filename, 'w', encoding='utf-8') as f:
                json.dump(self.todos, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"保存待办事项失败: {e}")

    def add_todo(self, task):
        """添加新的待办事项"""
        todo = {
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
            print(f"{i}. [{status}] {todo['task']}")
        print()

    def complete_todo(self, index):
        """标记待办事项为完成"""
        if 0 <= index < len(self.todos):
            self.todos[index]['completed'] = True
            self.save_todos()
            print("已标记为完成！")
        else:
            print("无效的索引")

    def delete_todo(self, index):
        """删除待办事项"""
        if 0 <= index < len(self.todos):
            deleted = self.todos.pop(index)
            self.save_todos()
            print(f"已删除: {deleted['task']}")
        else:
            print("无效的索引")


def main():
    """主函数"""
    todo_list = TodoList()

    while True:
        print("\n=== 待办事项管理 ===")
        print("1. 添加待办事项")
        print("2. 查看待办事项")
        print("3. 完成待办事项")
        print("4. 删除待办事项")
        print("5. 退出")

        choice = input("\n请选择操作 (1-5): ").strip()

        if choice == '1':
            task = input("请输入待办事项: ").strip()
            if task:
                todo_list.add_todo(task)
                print("添加成功！")

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
            except (ValueError, IndexError):
                print("无效的编号")

        elif choice == '5':
            print("再见！")
            break

        else:
            print("无效的选择，请重试")


if __name__ == '__main__':
    main()
