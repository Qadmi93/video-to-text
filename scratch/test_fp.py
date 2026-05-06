import flet as ft

def main(page: ft.Page):
    fp = ft.FilePicker()
    page.services.append(fp)
    page.update()
    print(f"FP ID: {fp._i}")
    page.window.close()

if __name__ == "__main__":
    ft.app(target=main)
