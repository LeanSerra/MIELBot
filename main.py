import signal
from functools import partial
from types import FrameType
from selenium import webdriver
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.firefox.options import Options
from telegram.ext import ApplicationBuilder, CommandHandler, Application
from botfunctions import poll_miel, oferta, notas, write_file


async def post_init(application: Application):
    await application.bot.set_my_commands(
        [
            ("oferta", "Realiza una consulta a la oferta de materias"),
            (
                "notas",
                "Realiza una consulta a tus notas",
            ),
        ]
    )


def sig_close(sig: int, frame: FrameType | None):
    print("Closing")
    if frame is not None:
        status = frame.f_locals.get("status")
        driver = frame.f_locals.get("driver")
        if status is not None:
            print("Writing file")
            write_file(".status", status)
        if driver is not None:
            print("Closing browser")
            driver.quit()
    exit(0)


def init_driver(dni: str, password: str) -> webdriver.Firefox:
    print("Initializing driver")
    options: Options = Options()
    options.add_argument("--headless")
    driver: webdriver.Firefox = webdriver.Firefox(options=options)
    driver.get("https://miel.unlam.edu.ar")
    ActionChains(driver=driver).send_keys_to_element(
        driver.find_element(By.ID, "usuario"), dni
    ).send_keys_to_element(driver.find_element(By.ID, "clave"), password).send_keys(
        Keys.RETURN
    ).perform()

    WebDriverWait(driver, 15).until(lambda e: e.find_element(By.ID, "menu-principal"))

    if driver.current_url != "https://miel.unlam.edu.ar/principal/interno/":
        print("No se pudo iniciar sesion")
        driver.close()
        exit(1)

    return driver


def load_status(driver: webdriver.Firefox) -> dict[int, dict[str, int]]:
    print("loading status")
    element_ids = [
        element.get_attribute("data-id")
        for element in driver.find_elements(
            By.CSS_SELECTOR, "body main div.curso-sortable div[data-id]"
        )
    ]

    status: dict[int, dict[str, int]] = {}

    for id in element_ids:
        if id is not None:
            id_int = int(id)
            status[id_int] = {
                "contenido": 0,
                "mensajeria": 0,
                "forov2": 0,
            }

    with open(".status", "+a") as f:
        f.seek(0)
        for line in f.readlines():
            parts: list[str] = line.split(",")
            if len(parts) == 4:
                currentID = int(parts[0])
                if currentID in status.keys():
                    status[currentID]["contenido"] = int(parts[1])
                    status[currentID]["mensajeria"] = int(parts[2])
                    status[currentID]["forov2"] = int(parts[3])
                else:
                    f.truncate(0)
                    break
    return status


def update_intraconsulta(
    driver: webdriver.Firefox, dni: int, password: str
) -> tuple[str, str]:
    original_window = driver.current_window_handle
    driver.switch_to.new_window("tab")
    driver.get("https://alumno2.unlam.edu.ar/")
    ActionChains(driver=driver).send_keys_to_element(
        driver.find_element(By.ID, "usuario"), dni
    ).send_keys_to_element(driver.find_element(By.ID, "clave"), password).send_keys(
        Keys.RETURN
    ).perform()

    WebDriverWait(driver, 10).until(
        lambda e: e.find_element(By.CSS_SELECTOR, ".nav-pills")
    )

    driver.execute_script("document.querySelector('#link03').click()")

    WebDriverWait(driver, 10).until(lambda e: e.find_element(By.TAG_NAME, "table"))

    oferta_table: str = driver.find_element(By.TAG_NAME, "table").get_attribute(
        "outerHTML"
    )

    driver.execute_script("document.querySelector('#link11').click()")

    WebDriverWait(driver, 10).until(
        lambda e: e.find_element(By.PARTIAL_LINK_TEXT, "Consultar Finales Desaprobados")
    )

    notas_table: str = driver.find_element(By.TAG_NAME, "table").get_attribute(
        "outerHTML"
    )

    driver.close()
    driver.switch_to.window(original_window)

    return (oferta_table, notas_table)


if __name__ == "__main__":
    signal.signal(signalnum=signal.SIGINT, handler=sig_close)

    dni: str = ""
    password: str = ""
    token: str = ""
    chat_id: int = 0

    with open(".token") as f:
        token = f.readline().strip()
        chat_id = int(f.readline())

    with open(".credentials") as f:
        dni = f.readline().strip()
        password = f.readline()

    if not dni.isdigit() or int(dni) < 1000000 or int(dni) > 99999999:
        print("DNI incorrecto")
        exit(1)

    if len(password) < 8:
        print("Contraseña incorrecta")
        exit(1)

    driver = init_driver(dni=dni, password=password)

    status = load_status(driver=driver)

    (oferta_table, notas_table) = update_intraconsulta(
        driver=driver, dni=dni, password=password
    )

    application = ApplicationBuilder().token(token).post_init(post_init).build()

    oferta_handler = CommandHandler(
        "oferta", partial(oferta, html=oferta_table, chat_id=chat_id)
    )

    notas_handler = CommandHandler(
        "notas", partial(notas, html=notas_table, chat_id=chat_id)
    )

    application.add_handler(oferta_handler)
    application.add_handler(notas_handler)

    job_queue = application.job_queue

    job_queue.run_repeating(
        poll_miel,
        interval=60,
        first=0,
        data={
            "driver": driver,
            "status": status,
            "application": application,
            "chatId": chat_id,
        },
    )

    print("Bot listening to commands")

    application.run_polling()
