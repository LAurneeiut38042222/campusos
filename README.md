# CampusOS

CampusOS este un portal demonstrativ pentru studenți, realizat cu **Python, Flask, HTML, CSS și MySQL**. Administratorul publică informațiile comune, iar fiecare student își vede propriile activități și date.

## Ce poți face

| Secțiune | Administrator | Student |
| --- | --- | --- |
| Orar | Adaugă, editează și șterge ore din orarul comun. | Consultă orarul comun. |
| Examene și termene | Își gestionează activitățile personale. | Își adaugă examene și termene și vede ce urmează. |
| Note | Publică și corectează note. | Își consultă propriile note. |
| Cămin | Adaugă taxele lunare și vede simulările de plată. | Consultă taxele proprii și poate simula plata. |
| Spălătorie | Consultă disponibilitatea. | Rezervă sau anulează un interval de două ore. |

Aplicația verifică suprapunerile din orar și acceptă o singură rezervare pe interval la spălătorie. Modul demonstrativ pentru cămin înregistrează simulări, fără transferuri de bani sau date de card.

## Pornire locală pe Windows

Ai nevoie de Docker Desktop pornit. Deschide Command Prompt în folderul care conține `compose.yaml`.

1. Creează fișierul de configurare și deschide-l în Notepad.

   ~~~cmd
   copy .env.example .env
   notepad .env
   ~~~

2. Completează în `.env`:

   - `MYSQL_PASSWORD` — parola bazei de date.
   - `ADMIN_PASSWORD` — parola inițială a contului de administrator, de cel puțin opt caractere.
   - `SECRET_KEY` — cheia sesiunilor Flask. Generează o valoare și copiaz-o în fișier.

     ~~~cmd
     docker run --rm python:3.12-slim python -c "import secrets; print(secrets.token_hex(32))"
     ~~~

   - `ADMIN_EMAIL` — adresa contului de administrator, implicit `admin@campusos.local`.
   - `APP_PORT` — portul local. Folosește `3001` dacă `3000` este deja ocupat.

3. Pornește proiectul.

   ~~~cmd
   docker compose up --build
   ~~~

4. Deschide [localhost:3000](http://localhost:3000) sau [localhost:3001](http://localhost:3001), în funcție de portul ales. Intră ca admin cu adresa și parola configurate la prima pornire. Pentru rolul de student, apasă **Creează cont**.

Dacă actualizezi o instalare CampusOS care folosește deja MySQL, copiază fișierul `.env` existent lângă noul `compose.yaml`. Aplicația creează tabelele lipsă la pornire. `docker compose down` elimină containerele și păstrează datele din volumul MySQL.

## Demonstrație

1. Ca admin, adaugă o oră în orarul comun.
2. Într-o fereastră Incognito, creează un cont de student și verifică dacă vezi ora în orar.
3. Din fereastra de admin, publică o notă și adaugă o taxă pentru acel cont.
4. Ca student, verifică nota, simulează plata taxei și rezervă un interval liber la spălătorie.

## Codul pe scurt

| Fișier | Rol |
| --- | --- |
| [app.py](app.py) | Rute Flask, autentificare, orar și activități |
| [campus.py](campus.py) | Cămin, spălătorie și note |
| [planner.py](planner.py) | Reguli de orar și alerte |
| [db.py](db.py) și [schema.sql](schema.sql) | Conexiunea la MySQL și structura tabelelor |
| [templates/](templates/) și [static/](static/) | Paginile HTML și stilurile |
| [compose.yaml](compose.yaml) | Configurația pentru rulare locală |

Când adminul salvează o oră, Flask verifică rolul contului. Apoi aplicația citește orele din ziua aleasă, verifică intervalul în `planner.py` și îl salvează în MySQL dacă este liber.

Fișierul `.env` conține configurarea locală și este ignorat de Git. Modelul de configurare este în `.env.example`.
