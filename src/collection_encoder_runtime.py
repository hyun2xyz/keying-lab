"""Hidden Windows encoder processes, bounded threads and pre-cleanup pipe diagnostics.

This changes process management only. The renderer's authored RGB stays intact.
"""
import datetime,json,os,subprocess
from pathlib import Path

_BASE_POPEN=subprocess.Popen

def install(log_path,encoder_threads=8):
    log_path=Path(log_path)
    def record(value):
        value['utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        with log_path.open('a',encoding='utf-8') as f:f.write(json.dumps(value,ensure_ascii=False)+'\n')
    class Pipe:
        def __init__(self,stream,process):self.stream,self.process,self.bytes_written=stream,process,0
        def __getattr__(self,key):return getattr(self.stream,key)
        def write(self,data):
            try:
                count=self.stream.write(data);self.bytes_written+=count;return count
            except BaseException as error:
                record({'event':'stdin_write_failed_before_cleanup','pid':self.process.pid,
                        'error':repr(error),'exit_status_before_cleanup':self.process.poll(),
                        'write_bytes':len(data),'prior_bytes_written':self.bytes_written})
                raise
    class Hidden(_BASE_POPEN):
        def __init__(self,args,*a,**kw):
            argv=args
            media=isinstance(argv,list) and Path(str(argv[0])).stem.lower() in ['ffmpeg','ffprobe']
            if media:
                if 'libx264' in argv and 'rawvideo' in argv and '-threads' not in argv:
                    # Mutate the reviewed argv list so the renderer's saved command
                    # records the actual invocation, including this thread budget.
                    argv[argv.index('-c:v'):argv.index('-c:v')]=['-threads',str(encoder_threads),'-filter_threads','2']
                if os.name=='nt':kw['creationflags']=kw.get('creationflags',0)|subprocess.CREATE_NO_WINDOW|subprocess.CREATE_NEW_PROCESS_GROUP
            super().__init__(argv,*a,**kw)
            if media:
                record({'event':'started','pid':self.pid,'argv':argv,'creationflags':kw.get('creationflags',0)})
                if self.stdin is not None and 'rawvideo' in argv and 'libx264' in argv:self.stdin=Pipe(self.stdin,self)
    subprocess.Popen=Hidden
    return record
