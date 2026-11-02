import argparse
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / ".estado" / "security" / "faces.dpapi"
MODEL = "buffalo_l"


def _enc(data):
    import win32crypt
    return win32crypt.CryptProtectData(data, "JARVIS face database", None, None, None, 0)


def _dec(data):
    import win32crypt
    return win32crypt.CryptUnprotectData(data, None, None, None, 0)[1]


def _load():
    return json.loads(_dec(DB.read_bytes()).decode()) if DB.exists() else {}


def _save(db):
    DB.parent.mkdir(parents=True, exist_ok=True)
    tmp = DB.with_suffix(".tmp")
    tmp.write_bytes(_enc(json.dumps(db, ensure_ascii=False).encode()))
    tmp.replace(DB)


def _engine():
    import cv2
    from insightface.app import FaceAnalysis
    app = FaceAnalysis(name=MODEL, providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1, det_size=(640, 640))
    return cv2, app


def enroll(name):
    cv2, app = _engine()
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW if os.name == "nt" else 0)
    if not cap.isOpened():
        raise RuntimeError("Não consegui abrir a webcam.")
    samples = []
    print("Olhe para a câmera e mova levemente o rosto. Coletando 12 amostras.")
    try:
        while len(samples) < 12:
            ok, frame = cap.read()
            if not ok:
                continue
            faces = app.get(frame)
            if len(faces) == 1 and faces[0].normed_embedding is not None:
                samples.append(faces[0].normed_embedding.tolist())
                print(f"Amostra {len(samples)}/12")
            elif len(faces) > 1:
                print("Deixe apenas a pessoa cadastrada no quadro.")
            cv2.imshow("Cadastro facial JARVIS - Q cancela", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                raise RuntimeError("Cadastro cancelado.")
            time.sleep(.25)
    finally:
        cap.release()
        cv2.destroyAllWindows()
    db = _load()
    db[name] = samples
    _save(db)
    print(f"Cadastro de {name} salvo protegido pelo Windows DPAPI.")


def _similaridade_maxima(amostras, embedding):
    """Produto escalar entre embeddings já normalizados."""
    melhor = -1.0
    for amostra in amostras:
        if len(amostra) != len(embedding):
            continue
        score = sum(float(a) * float(b) for a, b in zip(amostra, embedding))
        melhor = max(melhor, score)
    return melhor


def run(on_unknown, on_status=None, stop_event=None):
    cv2, app = _engine()
    db = _load()
    if not db:
        print('Nenhum familiar cadastrado. Execute: python -m security.face_guard enroll "Nome"')
        if on_status:
            on_status("not_enrolled", None, None)
        return

    known = [(name, samples) for name, samples in db.items()]
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW if os.name == "nt" else 0)
    if not cap.isOpened():
        raise RuntimeError("Não consegui abrir a webcam.")

    last_alert = 0
    last_status = None
    last_emit = 0
    reconhecido = False
    print("Reconhecimento facial ativo. A câmera será liberada após a primeira identificação.")
    if on_status:
        on_status("active", None, None)
    try:
        while stop_event is None or not stop_event.is_set():
            ok, frame = cap.read()
            if not ok:
                if on_status and (last_status != "camera_error" or time.time() - last_emit > 5):
                    on_status("camera_error", None, None)
                    last_status = "camera_error"
                    last_emit = time.time()
                time.sleep(.5)
                continue

            faces = app.get(frame)
            status = "no_face"
            recognized = None
            similarity = None
            if faces:
                status = "unknown"
                for face in faces:
                    embedding = face.normed_embedding
                    if embedding is None:
                        continue
                    best = -1.0
                    best_name = None
                    for name, samples in known:
                        score = _similaridade_maxima(samples, embedding)
                        if score > best:
                            best = score
                            best_name = name
                    if best >= 0.45:
                        status = "recognized"
                        recognized = best_name
                        similarity = round(best, 3)
                        break
                    similarity = round(best, 3) if best >= 0 else None
                if status == "unknown" and time.time() - last_alert > 60:
                    last_alert = time.time()
                    try:
                        on_unknown(int(time.time()))
                    except Exception as exc:
                        print("JARVIS: não consegui enviar o alerta de pessoa desconhecida:", repr(exc))

            if on_status and (status != last_status or time.time() - last_emit > 5):
                on_status(status, recognized, similarity)
                last_status = status
                last_emit = time.time()

            if status == "recognized":
                reconhecido = True
                break
            time.sleep(.15)
    finally:
        cap.release()
        if reconhecido:
            print("Identidade confirmada. Webcam liberada; reconhecimento encerrado.")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    enroll_parser = sub.add_parser("enroll")
    enroll_parser.add_argument("name")
    sub.add_parser("list")
    remove_parser = sub.add_parser("remove")
    remove_parser.add_argument("name")
    args = parser.parse_args()

    if args.cmd == "enroll":
        enroll(args.name)
    elif args.cmd == "list":
        print("\n".join(_load().keys()) or "Nenhum familiar cadastrado.")
    elif args.cmd == "remove":
        db = _load()
        db.pop(args.name, None)
        _save(db)
        print("Cadastro removido, se existia.")


if __name__ == "__main__":
    main()
