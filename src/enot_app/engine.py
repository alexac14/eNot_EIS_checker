import datetime as dt
import threading


class AutomationError(Exception):
    """Сообщения этой ошибки не должны содержать персональные данные."""


class StopRequested(AutomationError):
    pass


class StopToken:
    def __init__(self):
        self.event = threading.Event()
        self.reason = 'Остановлено пользователем.'

    def stop(self, reason='Остановлено пользователем.'):
        self.reason = reason
        self.event.set()

    def check(self):
        if self.event.is_set():
            raise StopRequested(self.reason)


class Runner:
    def __init__(self, driver, persist, progress=lambda _: None):
        self.driver, self.persist, self.progress = driver, persist, progress

    def execute(self, run, stop):
        def step(person, code, operation):
            stop.check()
            entry = dict(person=person+1 if person is not None else None, code=code, status='started')
            run['steps'].append(entry)
            self.persist(run)
            prefix = f'Участник {person+1}' if person is not None else 'Все участники'
            self.progress(f'{prefix}: {code}')
            try:
                operation()
                entry['status'] = 'confirmed'
            except Exception:
                entry['status'] = 'uncertain'
                raise
            finally:
                self.persist(run)
        try:
            self.driver.prepare()
            # Один проход по каждому разделу: не переключаем вкладки между людьми.
            step(None, 'ЗАГС: открыть раздел', self.driver.open_zags)
            for i, person in enumerate(run['people']):
                stop.check()
                step(i, 'ЗАГС: создать два запроса', lambda: self.driver.create_zags(person))
                for kind in ('расторжение брака', 'заключение брака'):
                    step(i, 'ЗАГС: подписать — '+kind,
                         lambda k=kind: self.driver.sign_record(person, k, run['signer']))
            step(None, 'Брачные договоры: открыть раздел', self.driver.open_contracts)
            for i, person in enumerate(run['people']):
                stop.check()
                step(i, 'Брачные договоры: создать запрос', lambda: self.driver.create_contract(person))
                step(i, 'Брачные договоры: подписать', lambda: self.driver.sign_record(person, None, run['signer']))
            step(None, 'еНот: финальное нажатие F5', self.driver.finalize_dispatch)
            run['f5_sent'] = True
            run['status'] = 'completed'
            run['note'] = ('По всем участникам подтверждены запросы ЗАГС, затем брачных договоров. '
                           'В активном окне еНот нажата F5. Получение данных сервером отдельно не проверялось. '
                           'Ответы просмотрите в еНот. Этапы 3 и 4 не выполнялись.')
        except StopRequested as e:
            run['status'], run['note'] = 'stopped', str(e)
        except AutomationError as e:
            run['status'], run['note'] = 'failed', str(e)
        except Exception:
            # Исключения библиотек могут содержать window_text с ФИО.
            run['status'], run['note'] = 'failed', 'Техническая ошибка. Последний шаг не подтверждён; проверьте еНот перед повтором.'
        finally:
            run['finished'] = dt.datetime.now().isoformat(timespec='seconds')
            self.persist(run)
        return run
