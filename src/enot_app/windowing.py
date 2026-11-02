import customtkinter as ctk

class CenteredToplevel(ctk.CTkToplevel):
    _deactivate_windows_window_header_manipulation = True
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)


        self.attributes('-alpha',0.0)
    def destroy(self):
        from enot_mockup_multi import cancel_callbacks
        if self.winfo_exists():cancel_callbacks(self)
        super().destroy()

def native_handle(window):
    import win32gui
    return win32gui.GetAncestor(window.winfo_id(),2)

def center_child(window,parent,modal=False,on_show=None):
    import win32api,win32gui
    window.transient(parent)
    jobs=[]
    def cancel(event):
        if event.widget is window:
            for job in jobs:
                try:window.after_cancel(job)
                except Exception:pass
    window.bind('<Destroy>',cancel,add='+')
    def position():
        if not window.winfo_exists() or not parent.winfo_exists():return
        owner=native_handle(parent)
        handle=native_handle(window)
        left,top,right,bottom=win32gui.GetWindowRect(owner)
        a,b,c,d=win32gui.GetWindowRect(handle)
        width,height=c-a,d-b
        work=win32api.GetMonitorInfo(win32api.MonitorFromWindow(owner,2))['Work']
        x=max(work[0],min((left+right-width)//2,work[2]-width))
        y=max(work[1],min((top+bottom-height)//2,work[3]-height))
        win32gui.SetWindowPos(handle,0,x,y,0,0,0x1|0x4|0x10)
    def show():
        if not window.winfo_exists():return
        if not window.winfo_viewable():
            jobs.append(window.after(5,show))
            return
        position()
        window.lift()
        window.attributes('-alpha',1.0)
        if modal:window.grab_set()
        if on_show:on_show()
    def prepare():
        if not window.winfo_exists():return
        position()

        jobs.append(window.after(20,show))
    jobs.append(window.after_idle(prepare))

def place_progress(window,rect,visible=True):
    import win32gui
    handle=native_handle(window)
    if not visible:
        win32gui.ShowWindow(handle,0)
        return
    left,top,right,bottom=rect
    a,b,c,d=win32gui.GetWindowRect(handle)
    width,height=c-a,d-b
    x=max(left,min(round(left+(right-left)*.53-width/2),right-width))
    y=max(top,min(round(top+(bottom-top)*.63),bottom-height-30))
    win32gui.SetWindowPos(handle,-1,x,y,0,0,0x1|0x10|0x40)
