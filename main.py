import signal
import re
from time import sleep
from types import FrameType
from selenium.webdriver.common.by import By
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains

# from selenium.webdriver.firefox.options import Options


def sigClose(sig: int, frame: FrameType | None):
    print("Writing file")
    writeFile(".status", status)
    exit(0)


def sendMessage(notifType: str, materia: str):
    print(notifType + " " + materia)


def writeFile(fileName: str, status: dict[int, dict]):
    with open(fileName, "w") as f:
        for key in status.keys():
            s = status[key]
            f.write(f"{key},{s['contenido']},{s['mensajeria']},{s['forov2']}\n")

if __name__ == "__main__":
    signal.signal(signalnum=signal.SIGINT, handler=sigClose)

    dni: str = ""
    password: str = ""
    token: str = ""

    with open(".token") as f:
        token = f.readline()

    with open(".credentials") as f:
        dni = f.readline()
        password = f.readline()

    if not re.search("[0-9]{3,3}?[0-9]{3,3}?[0-9]{1,2}", dni):
        print("DNI incorrecto")
        exit(1)

    if len(password) < 8:
        print("Contraseña incorrecta")
        exit(1)

    driver: webdriver.Firefox = webdriver.Firefox()
    driver.get("https://miel.unlam.edu.ar")
    ActionChains(driver=driver).send_keys_to_element(
        driver.find_element(By.ID, "usuario"), dni
    ).send_keys_to_element(driver.find_element(By.ID, "clave"), password).send_keys(
        Keys.RETURN
    ).perform()

    sleep(1)

    driver.get("https://miel.unlam.edu.ar/principal/interno/")

    if driver.current_url != "https://miel.unlam.edu.ar/principal/interno/":
        print("No se pudo iniciar sesion")
        driver.close()
        exit(1)

    elementIds = [
        element.get_attribute("data-id")
        for element in driver.find_elements(
            By.CSS_SELECTOR, "body main div.curso-sortable div[data-id]"
        )
    ]

    status: dict[int, dict] = {}

    for i, id in enumerate(elementIds):
        if id is not None:
            idInt = int(id)
            status[idInt] = {
                "contenido": 0,
                "mensajeria": 0,
                "forov2": 0,
            }

    with open(".status", "+a") as f:
        f.seek(0)
        for i, line in enumerate(f.readlines()):
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

    while True:
        driver.refresh
        for notifBadge in driver.find_elements(By.CSS_SELECTOR, ".w3-badge"):
            parentHref = notifBadge.find_element(By.XPATH, "..").get_attribute("href")
            notifCount = int(notifBadge.text)
            if parentHref is not None:
                idInt = int(parentHref.split("/")[-1])
                notifType = parentHref.split("/")[-4]
                previousCount = status[idInt][notifType]

                if notifCount > previousCount:
                    status[idInt][notifType] = notifCount
                    div = notifBadge.find_element(By.XPATH, "../../../..")
                    if div is not None:
                        writeFile(".status", status)
                        sendMessage(
                            notifType=notifType,
                            materia=div.find_element(
                                By.CLASS_NAME, "materia-titulo"
                            ).text,
                        )

        sleep(60 * 15)
