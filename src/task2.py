import asyncio
import os.path
import aiohttp
import aioconsole
import prettytable
from typing import Dict, List


async def img_download(
    path_folder: str,
    ln: str,
    counter: int,
    table_status: Dict[str, str],
    session: aiohttp.ClientSession,
) -> None:
    try:
        async with session.get(ln, ssl=False) as response:
            if response.status != 200:
                table_status[ln] = "Ошибка"
                return
            table_status[ln] = "Успех"
            content: bytes = await response.read()
            with open(f"{path_folder}/test_{counter}.jpg", "wb") as file:
                file.write(content)
    # except (aiohttp.ClientConnectionError, aiohttp.ClientResponseError, OSError):
    #     table_status[ln] = "Ошибка"
    except Exception:
        table_status[ln] = "Ошибка"


# https://images2.pics4learning.com/catalog/s/swamp_15.jpg
# https://bad-link-no-website-here.strange/img.png
# https://images2.pics4learning.com/catalog/p/parrot.jpg


def input_path_folder() -> str:
    path = input("Please, Enter a path to folder: ")
    while True:
        if not os.path.exists(path):
            path = input("Please, enter existed path to folder: ")
        else:
            try:
                test_file = f"{path}/test_file.txt"
                with open(test_file, "w") as f:
                    f.write("")
                os.remove(test_file)
                return path
            except (PermissionError, OSError):
                path = input("Нет доступа для записи, введите другой путь: ")


async def input_link() -> Dict[str, str]:
    status_table: Dict[str, str] = {}
    path_folder: str = input_path_folder()
    tasks: List[asyncio.Task[None]] = []
    async with aiohttp.ClientSession() as session:
        counter: int = 1
        while True:
            lnk = await aioconsole.ainput("Please, Enter a link: ")
            if lnk:
                tasks.append(
                    asyncio.create_task(
                        img_download(path_folder, lnk, counter, status_table, session)
                    )
                )
                counter += 1
            else:
                break
        if tasks and any(not task.done() for task in tasks):
            print("Ожидание завершения загрузок...")
        await asyncio.gather(*tasks, return_exceptions=True)
    return status_table


def print_table(result: Dict[str, str]) -> None:
    table = prettytable.PrettyTable()
    table.field_names = ["Ссылка", "Статус"]
    for key, value in result.items():
        table.add_row([key, value])
    table.align = "l"
    print(table)


async def main() -> None:
    result: Dict[str, str] = await input_link()
    print_table(result)


if __name__ == "__main__":
    asyncio.run(main())
