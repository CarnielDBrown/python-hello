import csv
import os


TODOS_FILE = "todos.csv"
todos = []


def add_one_task(title):
    todos.append(title)


def print_list():
    if not todos:
        print("No tasks found.")
        return

    for position, title in enumerate(todos, start=1):
        print(f"{position}. {title}")


def delete_task(number_to_delete):
    try:
        position = int(number_to_delete)
    except (TypeError, ValueError):
        print("Please enter a valid task number.")
        return

    if position < 1 or position > len(todos):
        print("Task number out of range.")
        return

    removed_task = todos.pop(position - 1)
    print(f"Deleted: {removed_task}")


def save_todos():
    with open(TODOS_FILE, "w", newline="", encoding="utf-8") as todo_file:
        writer = csv.writer(todo_file)
        writer.writerows([[title] for title in todos])


def load_todos():
    todos.clear()
    if not os.path.exists(TODOS_FILE):
        return

    with open(TODOS_FILE, "r", newline="", encoding="utf-8") as todo_file:
        reader = csv.reader(todo_file)
        rows = list(reader)

    if rows and rows[0] == ["title"]:
        rows = rows[1:]
    todos.extend(row[0] for row in rows if row)


def main():
    load_todos()
    while True:
        print("\nTodo List")
        print("1. Add task")
        print("2. View tasks")
        print("3. Delete task")
        print("4. Save tasks")
        print("5. Load tasks")
        print("q. Quit")
        choice = input("Choose an option: ").strip().lower()

        if choice == "1":
            title = input("Task title: ").strip()
            if title:
                add_one_task(title)
            else:
                print("Task title cannot be empty.")
        elif choice == "2":
            print_list()
        elif choice == "3":
            print_list()
            if todos:
                delete_task(input("Task number to delete: "))
        elif choice == "4":
            save_todos()
            print("Tasks saved.")
        elif choice == "5":
            load_todos()
            print("Tasks loaded.")
        elif choice == "q":
            save_todos()
            print("Tasks saved. Goodbye.")
            break
        else:
            print("Please choose a valid option.")


if __name__ == "__main__":
    main()