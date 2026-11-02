import datetime as dt
import threading


class AutomationError(Exception):
    pass


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
    def __init__(self, driver, persist, progress=lambda _: None, eis_driver=None):
        self.driver, self.persist, self.progress = driver, persist, progress
        self.eis_driver = eis_driver

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
            stop.check()
            if self.eis_driver is not None:
                self.eis_driver.prepare()
            if self.driver is not None:
                self.driver.prepare()

            if self.driver is not None:
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
            if self.eis_driver is not None:
                if self.driver is not None:
                    self.driver.guard()
                step(None, 'ЕИС: открыть регистр населения', lambda: (self.eis_driver.activate(), self.eis_driver.open_population()))
                for i, person in enumerate(run['people']):
                    step(i, 'ЕИС: отправить запрос в регистр населения', lambda: self.eis_driver.create_population(person))
                capacity_people = [(i,p) for i,p in enumerate(run['people']) if p.get('snils','').strip()]
                if capacity_people:
                    step(None, 'ЕИС: открыть запросы о дееспособности', self.eis_driver.open_capacity)
                    for i, person in capacity_people:
                        step(i, 'ЕИС: отправить запрос о дееспособности', lambda: self.eis_driver.create_capacity(person))
                run['capacity_skipped'] = [i+1 for i,p in enumerate(run['people']) if not p.get('snils','').strip()]
            stop.check()
            run['status'] = 'completed'
            if self.eis_driver is not None and self.driver is not None:
                run['note'] = 'Программа успешно отправила все предусмотренные запросы в клиенте ЕИС и еНоте.'
            elif self.eis_driver is not None:
                run['note'] = 'Программа успешно отправила все предусмотренные запросы в клиенте ЕИС.'
            else:
                run['note'] = 'Запросы еНота подписаны, финальное нажатие F5 выполнено.'
        except StopRequested as e:
            run['status'], run['note'] = 'stopped', str(e)
        except AutomationError as e:
            run['status'], run['note'] = 'failed', str(e)
        except Exception:
            run['status'], run['note'] = 'failed', 'Техническая ошибка. Последний шаг не подтверждён; проверьте еНот перед повтором.'
        finally:
            if run['status'] != 'completed':
                last = run['steps'][-1] if run['steps'] else None
                if last:
                    who = f"Участник {last['person']}: " if last.get('person') else ''
                    run['note'] = who+last['code']+'.\n'+run['note']+'\nУже отправленные запросы не отменены. Перед повтором проверьте журналы ЕИС и еНота.'
            run['finished'] = dt.datetime.now().isoformat(timespec='seconds')
            self.persist(run)
        return run
