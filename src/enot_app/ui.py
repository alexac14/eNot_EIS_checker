import datetime as dt
import json
import os
from pathlib import Path
import queue
import threading
from .windowing import center_child, place_progress, native_handle, CenteredToplevel
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk
import enot_mockup_multi as multi
from enot_mockup import Field, BG, WHITE, TEXT, MUTED, F, BORDER_IDLE
from enot_mockup_deals import DealsSideApp, Deal, TextButton, pill, GREY_T, TRACK
from .domain import validate
from .storage import Repository, data_directory, new_run, atomic
from .engine import Runner, StopToken
from .driver import WindowsDriver, InputMonitor
from .eis_driver import EISDriver
from . import VERSION


class ValidationField(Field):
    def __init__(self, *args, **kwargs):
        self.error = ''
        self.touched = False
        super().__init__(*args, **kwargs)

    def _refresh(self):
        if self.error:
            self.entry.configure(border_color='#CE3545')
        else:
            super()._refresh()

    def set_error(self, error):
        self.error = error if self.touched else ''
        job = self.__dict__.get('_anim_jobs', {}).pop('p', None)
        if job:
            self.after_cancel(job)
        self.entry.configure(border_color='#CE3545' if self.error else BORDER_IDLE)


    def _focus_out(self,event):
        self.touched=True
        super()._focus_out(event)
        top=self.winfo_toplevel()
        if hasattr(top,'check'):self.after_idle(top.check)

def make_field(parent, key, compact=False):
    for k,label,ph,req,cap,live,blur in multi.SPEC:
        if k == key:
            return ValidationField(parent, None if compact else label, ph, required=req,
                                   caption=None if compact else cap, live_format=live,
                                   on_blur_format=blur, height=38 if compact else 40)


multi.make_field = make_field


def deal_object(record):
    history = [(r['kind'], r.get('finished',r['started']).replace('T',' '))
               for r in record.get('runs',[]) if r['status']=='completed']
    obj = Deal(record['title'], record['date'], record['people'], history)
    obj.record = record
    return obj


def step_text(step):
    who = f"Участник {step['person']}" if step.get('person') else 'Все участники'
    return f"{who}: {step['code']} — {step['status']}"


class App(DealsSideApp):
    def init_state(self):
        self.repo = Repository(data_directory())
        self.repo.acquire()
        self.deals = [deal_object(d) for d in self.repo.list()]
        self.current = None
        self.quick_people = [{}]
        self.seen = set()
        self._validation_job = self._save_job = None
        self.busy = False
        self.messages = queue.Queue()
        self.session_run = None

    def __init__(self):
        super().__init__()
        self.title('Проверки еНот & ЕИС')
        try:
            self.iconbitmap(str(Path(__file__).parent/'app.ico'))
        except tk.TclError:
            pass
        scale = self.scale()
        width = min(1354, max(1040,int(self.winfo_screenwidth()/scale)-40))
        height = min(760, max(620,int(self.winfo_screenheight()/scale)-90))
        self.minsize(1040, 620)
        self._center(width,height)
        self.protocol('WM_DELETE_WINDOW', self.close)
        tools = ctk.CTkFrame(self, fg_color=BG, height=30)

        tools.pack(fill='x', padx=32, pady=(0,8), before=self.winfo_children()[0])
        ctk.CTkLabel(tools,text='Проверки еНот & ЕИС',font=F(12,'bold'),text_color=MUTED).pack(side='left')
        ctk.CTkLabel(tools,text='Powered by Alexandr Andreev',font=F(11),text_color='#8C9AAF').pack(side='left',padx=18)
        for text,command in [('Настройки',self.settings),('Диагностика',self.diagnose),('История',self.history),('Папка данных',self.data_folder)]:
            ctk.CTkButton(tools,text=text,command=command,width=105,height=28,fg_color=TRACK,text_color=TEXT,font=F(12)).pack(side='right',padx=3)
        self.status = ctk.CTkLabel(self.go.master, text='',font=F(11),text_color='#BD283A',anchor='w',justify='left',wraplength=1000)
        self.status.pack(fill='x', before=self.go, pady=(5,0))
        self.key.btn.configure(width=125)
        self.key.bind('<Configure>',lambda e:self.key.text.configure(wraplength=max(140,self.key.winfo_width()/self.key._get_widget_scaling()-220)),add=True)
        self.who.track.bind('<ButtonRelease-1>',lambda e:self.after_idle(self.check),add=True)
        for button in self.who.btns:
            button.bind('<ButtonRelease-1>',lambda e:self.after_idle(self.check),add=True)
        self.after(300,self.check)
        self.after(150,self.poll)
        self.bind_all('<Button-1>',self._background_click,add='+')
        if self.repo.issues:
            self.after(300,lambda:messagebox.showwarning('Не все сделки открыты','Есть повреждённые или недоступные файлы сделок. Они не изменены. Проверьте папку данных.',parent=self))

    def _chg(self):
        self.update_count(len(self.board.rows))
        if self._validation_job:
            self.after_cancel(self._validation_job)
        self._validation_job = self.after(200,self.check)
        if self._save_job:
            self.after_cancel(self._save_job)
        self._save_job = self.after(600,self.save_current)

    def check(self):
        self._validation_job = None
        if self.busy or not hasattr(self,'status'):
            return
        result = validate([r.values() for r in self.board.rows], self.who.value, self.key.confirmed,self.seen)
        self.validation = result
        for i,row in enumerate(self.board.rows):
            for key,field in row.fields.items():
                field.set_error(result.errors.get((i,key),''))
        errors = [f'Участник {i+1}: {text}' for (i,k),text in result.errors.items() if i>=0 and self.board.rows[i].fields[k].touched]
        self.status.configure(text='\n'.join(errors[:2]) + ('\nЕсть другие ошибки ввода.' if len(errors)>2 else ''))


        self.go.label.configure(text_color=WHITE if not result.errors else '#CFD9F4')
        self.go.command = self.start if not result.errors else lambda:None

    def _background_click(self,event):
        widget=event.widget
        try:
            top=widget.winfo_toplevel()
            node=widget
            while node is not top:
                if isinstance(node,(tk.Entry,tk.Text,tk.Button,ctk.CTkEntry,ctk.CTkTextbox,ctk.CTkButton,TextButton)):
                    return
                if hasattr(node,'command') or node.__class__.__name__ in ('NavItem','PrimaryButton','CloseMark'):
                    return
                node=node.master
            top.focus_set()
        except (tk.TclError,AttributeError):pass

    def data_folder(self):
        win=CenteredToplevel(self)
        win.title('Папка данных')
        win.geometry('700x210')
        ctk.CTkLabel(win,text='Данные хранятся на этом компьютере:',font=F(15)).pack(pady=(25,10))
        entry=ctk.CTkEntry(win,width=650,font=F(13))
        entry.insert(0,str(self.repo.root))
        entry.configure(state='readonly')
        entry.pack(padx=20,fill='x')
        ctk.CTkButton(win,text='Открыть в Проводнике',command=lambda:os.startfile(self.repo.root)).pack(pady=22)
        center_child(win,self)
        return win

    def save_current(self):
        self._save_job = None
        super().save_current()
        if self.current:
            self.current.record['people'] = [r.values() for r in self.board.rows]
            self.repo.save(self.current.record)

    def enter_deal(self, deal):
        if self.busy:
            return
        super().enter_deal(deal)
        self.update_header()
        self.reset_key()

    def enter_quick(self, keep_rows=False):
        if self.busy:
            return
        super().enter_quick(keep_rows)
        if hasattr(self,'key'):
            self.reset_key()

    def reset_key(self):
        if self.key.confirmed:
            self.key.toggle()
        if hasattr(self,'status'):
            self.check()

    def update_header(self):
        if not self.current:
            return
        d = self.current
        self.header.show_deal(d,self.delete_deal)
        path = self.repo.folder(d.record)
        self.header.sub.configure(text=d.history_text()+'\n'+str(path/'participants.json'),wraplength=720)
        if d.record.get('runs') and d.record['runs'][-1]['status'] != 'completed':
            pill(self.header.meta,'Есть незавершённый запуск','#B2293A','#FFE7EB')

    def _create(self, title, date, keep):
        if date:
            try:
                dt.datetime.strptime(date,'%d.%m.%Y')
            except ValueError:
                messagebox.showerror('Дата сделки','Укажите существующую дату дд.мм.гггг.',parent=self)
                return
        self.save_current()
        people = [r.values() for r in self.board.rows] if keep else [{}]
        record = self.repo.create(title,date,people)
        d = deal_object(record)
        self.deals.insert(0,d)
        self.enter_deal(d)
        self.toast('Сделка сохранена на этом компьютере.')

    def delete_deal(self):
        if not self.current or self.busy:
            return
        if messagebox.askyesno('Удалить сделку','Удалить участников и всю историю этой сделки с диска? Это действие необратимо.',parent=self):
            if self._save_job:
                self.after_cancel(self._save_job)
                self._save_job = None
            d = self.current
            self.repo.delete(d.record)
            self.deals.remove(d)
            self.current = None
            self.board.load(self.quick_people)
            self.enter_quick(keep_rows=True)

    def history(self):
        self.save_current()
        runs = self.current.record.get('runs',[]) if self.current else ([self.session_run] if self.session_run else [])
        win = CenteredToplevel(self)
        win.title('История запусков')
        win.geometry('780x530')
        box = ctk.CTkTextbox(win,font=F(13),wrap='word')
        box.pack(fill='both',expand=True,padx=16,pady=16)
        lines = []
        for run in reversed(runs):
            lines += [f"{run['started']} · {run['kind']} · {run['status']}",run.get('note','')]
            lines += ['  '+step_text(s) for s in run['steps']]
            lines += ['']
        box.insert('1.0','\n'.join(lines) or 'Запусков пока нет.')
        box.configure(state='disabled')
        center_child(win,self)
        return win

    def settings(self):
        win = CenteredToplevel(self)
        win.title('Настройки подписи и хранения · '+VERSION)
        win.geometry('640x425')
        win.transient(self)
        fields = {}
        for key,label in [('notary','ФИО нотариуса в сертификате'),('acting','ФИО ВРИО в сертификате')]:
            ctk.CTkLabel(win,text=label,font=F(14)).pack(anchor='w',padx=22,pady=(14,3))
            entry = ctk.CTkEntry(win,font=F(15))
            entry.insert(0,self.repo.settings[key])
            entry.pack(fill='x',padx=22)
            fields[key] = entry
        encrypt = tk.BooleanVar(value=self.repo.settings['encrypt'])
        ctk.CTkCheckBox(win,text='Шифровать новые записи средствами Windows (DPAPI)',variable=encrypt).pack(anchor='w',padx=22,pady=20)
        ctk.CTkLabel(win,text='Зашифрованные файлы привязаны к учётной записи Windows.\nПеренос на другой компьютер потребует отдельного экспорта.\nУже сохранённая история автоматически не перешифровывается.',font=F(12),justify='left').pack(anchor='w',padx=22)
        def save():
            if not all(e.get().strip() for e in fields.values()):
                messagebox.showerror('Настройки','Заполните оба ФИО.',parent=self)
                return
            self.repo.settings.update({k:e.get().strip() for k,e in fields.items()})
            self.repo.settings['encrypt'] = encrypt.get()
            self.repo.save_settings()
            win.destroy()
        ctk.CTkButton(win,text='Сохранить настройки',command=save).pack(pady=20)
        center_child(win,self,modal=True)
        return win

    def diagnose(self):
        if self.busy:
            return
        self.withdraw()
        def worker():
            import pythoncom
            pythoncom.CoInitialize()
            try:
                paths=[]
                errors=[]
                for name,cls in [('enot',WindowsDriver),('eis',EISDriver)]:
                    try:
                        report=cls(self.repo.settings,StopToken()).diagnose()
                        path=self.repo.root/('diagnostics-'+name+'.json')
                        atomic(path,report)
                        paths.append(str(path))
                    except Exception:
                        errors.append('Не удалось прочитать '+('еНот' if name=='enot' else 'клиент ЕИС')+'. Проверьте запуск, закрытые диалоги и одинаковые права приложений.')
                self.messages.put(('diagnostic','\n'.join(['Техническая структура без значений полей и снимков:',*paths,*errors])))
            except Exception:
                self.messages.put(('diagnostic','Не удалось сохранить диагностику. Проверьте доступ к папке данных.'))
            finally:
                pythoncom.CoUninitialize()
        self.busy = True
        threading.Thread(target=worker,daemon=True).start()

    def start(self):
        if self.busy:
            return
        self.check()
        result = self.validation
        if result.errors:
            text = '\n'.join((f'Участник {i+1}: ' if i>=0 else '')+t for (i,k),t in result.errors.items())
            messagebox.showerror('Проверьте данные',text,parent=self)
            return
        warnings = list(result.warnings)
        if self.current and any(r['status'] != 'completed' for r in self.current.record['runs']):
            warnings.append('Есть незавершённый запуск. Уже созданные запросы могут остаться в еНот. Проверьте их вручную перед новым запуском.')
        if warnings:
            if not messagebox.askyesno('Предупреждения','\n\n'.join(warnings)+'\n\nПродолжить?',default='no',parent=self):
                return
        self.save_current()
        deal = self.current.record if self.current else None
        repeat = bool(self.current and self.current.primary_done)
        run = new_run(result.people,self.who.value,repeat)
        self.session_run = run
        if deal is not None:
            deal['runs'].append(run)
        self.repo.save_run(deal,run)
        self.busy = True
        self.stop = StopToken()
        self.withdraw()
        self.overlay = ctk.CTkToplevel(self)
        self.overlay.title('Выполняются проверки еНот & ЕИС')
        self.overlay.attributes('-topmost',True)
        self.overlay.geometry('680x150')
        self.overlay.update_idletasks()
        import win32gui
        self.overlay_rect=win32gui.GetWindowRect(native_handle(self))
        place_progress(self.overlay,self.overlay_rect)
        self.overlay.resizable(False,False)
        ctk.CTkLabel(self.overlay,text='Идёт проверка. Не трогайте мышь и клавиатуру.',font=F(15,'bold')).pack(padx=15,pady=(12,3))
        self.progress_label = ctk.CTkLabel(self.overlay,text='Подготовка еНота и клиента ЕИС…',font=F(13))
        self.progress_label.pack()
        ctk.CTkButton(self.overlay,text='Остановить · F8',command=self.stop.stop).pack(pady=8)
        self.overlay.protocol('WM_DELETE_WINDOW',self.stop.stop)
        def worker():
            import pythoncom
            pythoncom.CoInitialize()
            monitor = InputMonitor(self.stop)
            try:
                driver = WindowsDriver(self.repo.settings,self.stop)
                eis = EISDriver(self.repo.settings,self.stop)

                eis.prepare()
                driver.prepare()
                rect=driver.main.rectangle()
                self.overlay_rect=(rect.left,rect.top,rect.right,rect.bottom)
                def visibility(visible):
                    ack=threading.Event()
                    self.messages.put(('overlay',(visible,ack)))
                    if not ack.wait(5):self.stop.stop('Не удалось обновить окно прогресса.')
                    self.stop.check()
                driver.progress_visibility=visibility
                def eis_visibility(visible):
                    rect=eis.main.rectangle()
                    self.overlay_rect=(rect.left,rect.top,rect.right,rect.bottom)
                    visibility(visible)
                eis.progress_visibility=eis_visibility
                visibility(True)
                monitor.start()
                driver.prepare = lambda:None
                eis.prepare = lambda:None
                Runner(driver,lambda r:self.repo.save_run(deal,r),lambda s:self.messages.put(('progress',s)),eis_driver=eis).execute(run,self.stop)
            except Exception as exc:
                from .engine import AutomationError
                run['status'] = 'failed'
                run['note'] = ('Техническая ошибка или ошибка сохранения. Последний шаг мог выполниться. Проверьте еНот перед повтором.' if run['steps'] else
                               str(exc) if isinstance(exc,AutomationError) else 'Не удалось подготовить еНот, клиент ЕИС или контроль остановки. Запросы не начинались. Проверьте запуск приложений и их права.')
                try:
                    self.repo.save_run(deal,run)
                except Exception:
                    run['note'] += '\nНе удалось сохранить историю на диск.'
            finally:
                monitor.close()
                pythoncom.CoUninitialize()
                self.messages.put(('done',run))
        self.after(400,lambda:threading.Thread(target=worker,daemon=True).start())

    def poll(self):
        try:
            while True:
                kind,payload = self.messages.get_nowait()
                if kind == 'progress':
                    self.progress_label.configure(text=payload)
                elif kind == 'overlay':
                    visible,ack=payload
                    try:place_progress(self.overlay,self.overlay_rect,visible)
                    finally:ack.set()
                elif kind == 'diagnostic':
                    self.busy = False
                    self.deiconify()
                    messagebox.showinfo('Диагностика',payload,parent=self)
                elif kind == 'done':
                    self.overlay.destroy()
                    self.busy = False
                    self.deiconify()
                    if self.current:
                        record = self.current.record
                        self.current.history = deal_object(record).history
                        self.update_header()
                        self.refresh_nav()
                    for step in payload['steps']:
                        if step['status'] in ('confirmed','uncertain') and 'создать' in step['code']:
                            p = payload['people'][step['person']-1]
                            self.seen.add(((p['fio'].casefold(),p['dob']),dt.date.today().isoformat()))
                    if payload['status']=='completed':
                        messagebox.showinfo('Проверки завершены',payload['note'],parent=self)
                    else:
                        text = payload['note']+'\n\n'+'\n'.join(step_text(s) for s in payload['steps'])
                        messagebox.showerror('Проверки не завершены',text,parent=self)
                    if not self.current:
                        self.board.load([{}])
                        self.quick_people = [{}]
                        self.session_run = None
                        payload['people'].clear()

                    self.reset_key()
                    self.check()
        except queue.Empty:
            pass
        choice = (self.who.value,self.key.confirmed)
        if choice != getattr(self,'_choice_state',None) and not self.busy:
            self._choice_state = choice
            self.check()
        self.after(150,self.poll)

    def close(self):
        if self.busy:
            if hasattr(self,'stop'):
                self.stop.stop()
            return
        self.save_current()
        self.repo.close()
        self.destroy()

    def report_callback_exception(self, exc, value, tb):
        messagebox.showerror('Ошибка приложения','Операция не завершена. Проверьте доступ к папке данных. Персональные данные в технический журнал не записываются.',parent=self)
