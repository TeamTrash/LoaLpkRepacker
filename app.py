"""Small local GUI for verified, complete-folder LPK replacement."""
from pathlib import Path
from contextlib import closing
import hashlib
import json
import os
import queue
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

VERSION = '0.2.1'
ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
BACKEND = ROOT / 'backend' / 'LpkBulkRepack.exe'
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def call_backend(args, cancel, emit):
    process = subprocess.Popen([str(BACKEND), *map(str, args)], stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                               errors='replace', creationflags=FLAGS)
    def monitor():
        while process.poll() is None:
            if cancel.wait(.2):
                if process.poll() is None:
                    process.terminate()
                return
    threading.Thread(target=monitor, daemon=True).start()
    lines = []
    for line in process.stdout:
        lines.append(line.rstrip())
        emit(line.rstrip())
    code = process.wait()
    if cancel.is_set():
        raise RuntimeError('Operación cancelada. No se publicó el archivo de salida.')
    if code:
        raise RuntimeError('El motor no completó la operación.\n' + '\n'.join(lines[-12:]))
    return lines


def normalize_db_padding(path):
    """Restore PKCS#7 page tails in the known 1024/16 Lost Ark DB layout.

    Only a temporary snapshot is passed here, never the user's source DB.
    The backend independently checks the original archive's padding convention.
    """
    repaired = 0
    with path.open('r+b') as stream:
        header = stream.read(100)
        if header[:16] != b'SQLite format 3\x00' or header[16:18] != b'\x04\x00' or header[20] != 16:
            return 0
        stream.seek(0, 2)
        length = stream.tell()
        if length % 1024:
            raise ValueError('Tamaño de página SQLite incorrecto: ' + str(path))
        # Read in batches to avoid a seek for every page in large DBs.
        for offset in range(0, length, 1024 * 4096):
            stream.seek(offset)
            block = bytearray(stream.read(min(1024 * 4096, length - offset)))
            dirty = False
            for end in range(1024, len(block) + 1, 1024):
                if block[end-16:end] != b'\x10' * 16:
                    block[end-16:end] = b'\x10' * 16
                    repaired += 1
                    dirty = True
            if dirty:
                stream.seek(offset)
                stream.write(block)
    return repaired


def repack(original, database, destination, cancel, emit):
    original, database, destination = map(lambda p: Path(p).resolve(), (original, database, destination))
    if not original.is_file() or not database.is_dir():
        raise ValueError('Selecciona un LPK original y una carpeta extraída completa.')
    if destination.suffix.lower() != '.lpk':
        raise ValueError('El destino debe terminar en .lpk.')
    if destination.exists() or destination == original:
        raise ValueError('Elige un archivo de salida nuevo. No se sobrescriben archivos.')
    if destination.is_relative_to(database):
        raise ValueError('Guarda el resultado fuera de la carpeta de entrada.')
    if not destination.parent.is_dir():
        raise ValueError('La carpeta de destino no existe.')
    files = sorted(p for p in database.rglob('*') if p.is_file())
    if not files:
        raise ValueError('La carpeta está vacía.')
    if any(p.is_symlink() or p.is_junction() for p in database.rglob('*')):
        raise ValueError('No se admiten enlaces dentro de la carpeta.')
    if any(p.name.endswith(('-wal', '-journal', '-shm')) for p in files):
        raise ValueError('Guarda los cambios y cierra el editor (WAL/journal presente).')
    stats = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in files}
    total = sum(v[0] for v in stats.values())
    if shutil.disk_usage(destination.parent).free < original.stat().st_size + total * 2 + 64 * 1024**2:
        raise ValueError('No hay espacio suficiente para la copia de trabajo y el LPK.')
    emit('Comprobando correspondencia de la carpeta con el LPK…')
    mapping = call_backend(['map', original, database], cancel, emit)
    # The backend folder-verified command additionally rejects extra and empty files.
    with tempfile.TemporaryDirectory(prefix='loa_repack_', dir=destination.parent) as temp:
        snapshot = Path(temp) / 'source'
        snapshot.mkdir()
        sqlite_count = 0
        padding_repairs = {}
        for i, source in enumerate(files, 1):
            if cancel.is_set():
                raise RuntimeError('Operación cancelada.')
            target = snapshot / source.relative_to(database)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            with target.open('rb') as stream:
                sqlite_header = stream.read(16) == b'SQLite format 3\x00'
            if source.suffix.lower() == '.db' and not sqlite_header:
                raise ValueError('Base SQLite no válida: ' + str(source))
            if sqlite_header:
                repaired = normalize_db_padding(target)
                if repaired:
                    padding_repairs[str(source.relative_to(database))] = repaired
                    emit(f'Restaurado relleno de cifrado: {source.name}, {repaired} páginas.')
                with closing(sqlite3.connect(target.as_uri() + '?mode=ro', uri=True)) as connection:
                    connection.set_progress_handler(lambda: int(cancel.is_set()), 10000)
                    if connection.execute('PRAGMA integrity_check').fetchall() != [('ok',)]:
                        raise ValueError('Integridad SQLite incorrecta: ' + str(source))
                sqlite_count += 1
            if i % 50 == 0:
                emit(f'Copiados y comprobados {i}/{len(files)} archivos…')
        current = sorted(p for p in database.rglob('*') if p.is_file())
        if current != files or any((p.stat().st_size, p.stat().st_mtime_ns) != stats[p] for p in files):
            raise ValueError('La carpeta cambió durante la copia. Cierra los editores y vuelve a intentar.')
        temporary_output = Path(temp) / 'verified.lpk'
        emit('Comparando, cifrando cambios y verificando todas las entradas…')
        lines = call_backend(['folder-verified', original, snapshot, temporary_output], cancel, emit)
        if cancel.is_set():
            raise RuntimeError('Operación cancelada.')
        emit('Calculando SHA256 del resultado…')
        digest = hashlib.sha256()
        with temporary_output.open('rb') as stream:
            while block := stream.read(4 * 1024**2):
                if cancel.is_set():
                    raise RuntimeError('Operación cancelada.')
                digest.update(block)
        report = {'version': VERSION, 'original': str(original), 'folder': str(database),
                  'files': len(files), 'sqlite_checked': sqlite_count, 'output': str(destination), 'sha256': digest.hexdigest(),
                  'sqlite_integrity': 'ok', 'padding_repairs': padding_repairs,
                  'verification': lines}
        # On Windows rename refuses an existing destination; publish only after verification.
        os.rename(temporary_output, destination)
        report_path = Path(str(destination) + '.verification.json')
        try:
            with report_path.open('x', encoding='utf-8') as stream:
                json.dump(report, stream, ensure_ascii=False, indent=2)
        except OSError as exc:
            emit('LPK verificado y guardado; no se pudo guardar el informe: ' + str(exc))
        emit('Listo: ' + str(destination))
        return report


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f'Loa LPK Repacker · {VERSION}')
        self.geometry('850x570')
        self.minsize(720, 500)
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.running = False
        self.values = [tk.StringVar() for _ in range(3)]
        self.controls = []
        frame = ttk.Frame(self, padding=22)
        frame.pack(fill='both', expand=True)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text='Repack de carpeta completa', font=('Segoe UI', 20, 'bold')).grid(row=0, column=0, columnspan=3, sticky='w')
        ttk.Label(frame, text='Incluye toda la carpeta y verifica cada archivo contra el LPK generado.').grid(row=1, column=0, columnspan=3, sticky='w', pady=(4, 20))
        for i, label in enumerate(['LPK original', 'Carpeta extraída', 'Nuevo LPK']):
            ttk.Label(frame, text=label).grid(row=i+2, column=0, sticky='w', padx=(0, 12), pady=8)
            field = ttk.Entry(frame, textvariable=self.values[i])
            field.grid(row=i+2, column=1, sticky='ew', pady=8)
            button = ttk.Button(frame, text='Examinar…', command=lambda n=i: self.browse(n))
            button.grid(row=i+2, column=2, padx=(10, 0))
            self.controls.extend([field, button])
        ttk.Label(frame, text='Guarda los cambios y cierra el editor de bases antes de iniciar.\nLa salida debe ser un archivo nuevo. El original se conserva.').grid(row=5, column=0, columnspan=3, sticky='w', pady=12)
        actions = ttk.Frame(frame)
        actions.grid(row=6, column=0, columnspan=3, sticky='ew')
        start = ttk.Button(actions, text='Crear y verificar repack', command=self.start)
        start.pack(side='left')
        self.controls.append(start)
        self.stop = ttk.Button(actions, text='Cancelar', state='disabled', command=self.cancel.set)
        self.stop.pack(side='left', padx=10)
        self.progress = ttk.Progressbar(frame, mode='indeterminate')
        self.progress.grid(row=7, column=0, columnspan=3, sticky='ew', pady=12)
        self.log = tk.Text(frame, height=12, wrap='word', state='disabled', font=('Consolas', 10))
        self.log.grid(row=8, column=0, columnspan=3, sticky='nsew')
        frame.rowconfigure(8, weight=1)
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.poll)

    def browse(self, index):
        if index == 2:
            path = filedialog.asksaveasfilename(title='Guardar nuevo LPK', defaultextension='.lpk', initialfile='data2_repacked.lpk', filetypes=[('LPK', '*.lpk')])
        elif index == 1:
            path = filedialog.askdirectory(title='Seleccionar carpeta extraída completa')
        else:
            path = filedialog.askopenfilename(title='Seleccionar LPK original', filetypes=[('LPK', '*.lpk')])
        if path:
            self.values[index].set(path)

    def start(self):
        paths = [value.get().strip() for value in self.values]
        if not all(paths):
            messagebox.showerror('Faltan archivos', 'Selecciona el LPK original, la carpeta y la salida.')
            return
        self.running = True
        self.cancel.clear()
        for control in self.controls:
            control.configure(state='disabled')
        self.stop.configure(state='normal')
        self.progress.start()
        def worker():
            try:
                report = repack(*paths, self.cancel, lambda line: self.events.put(('log', line)))
                self.events.put(('done', report['output']))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        while not self.events.empty():
            kind, text = self.events.get()
            self.log.configure(state='normal')
            self.log.insert('end', text + '\n')
            self.log.see('end')
            self.log.configure(state='disabled')
            if kind != 'log':
                self.running = False
                self.progress.stop()
                for control in self.controls:
                    control.configure(state='normal')
                self.stop.configure(state='disabled')
                if kind == 'done':
                    messagebox.showinfo('Repack verificado', 'Archivo guardado:\n' + text)
                else:
                    messagebox.showerror('Operación no completada', text)
        self.after(100, self.poll)

    def close(self):
        if self.running:
            self.cancel.set()
            messagebox.showinfo('Cancelando', 'Espera a que termine la cancelación antes de cerrar.')
        else:
            self.destroy()


if __name__ == '__main__':
    if len(sys.argv) == 5 and sys.argv[1] == '--repack':
        try:
            repack(*sys.argv[2:], threading.Event(), lambda line: None)
        except Exception:
            import traceback
            Path(sys.argv[4] + '.error.txt').write_text(traceback.format_exc(), encoding='utf-8')
            sys.exit(1)
    elif len(sys.argv) == 3 and sys.argv[1] == '--self-test':
        app = App()
        app.update()
        assert BACKEND.is_file()
        app.destroy()
        Path(sys.argv[2]).write_text(json.dumps({'version': VERSION, 'gui': 'ok', 'backend': str(BACKEND)}))
    else:
        App().mainloop()
