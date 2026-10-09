#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdarg.h>
#include "host_config.h"
#define NUM_IMAGES 2000
#define ESP_OK 0
#define ESP_ERR_NVS_NOT_FOUND 2
#define ESP_PARTITION_TYPE_DATA 1
#define ESP_PARTITION_SUBTYPE_ANY 0
#define NVS_READWRITE 1
#define MALLOC_CAP_SPIRAM 1
#define MALLOC_CAP_8BIT 2
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define TFLITE_MODEL_SHA256 "model"
#define IMAGE_LIST_SHA256 "images"
static char identity[] = "config1";
#define BENCHMARK_CONFIG_SHA256 identity
typedef int esp_err_t;
typedef int nvs_handle_t;
typedef struct { size_t size; } esp_partition_t;
static esp_partition_t partition = {1024 * 1024};
static uint8_t flash[1024 * 1024], arena[16384];
static uint64_t attempt_value, staged_value;
static int erase_count, write_count, fail_write, fail_bytes, fail_commit;

void *memset(void *dst, int value, size_t n) { uint8_t *p=dst; while(n--) *p++=value; return dst; }
void *memcpy(void *dst, const void *src, size_t n) { uint8_t *d=dst; const uint8_t *s=src; while(n--) *d++=*s++; return dst; }
int memcmp(const void *a, const void *b, size_t n) { const uint8_t *x=a,*y=b; while(n--) {if(*x!=*y) return *x-*y; ++x;++y;} return 0; }
int snprintf(char *dst, size_t n, const char *fmt, ...) {
    (void)fmt; va_list args; va_start(args,fmt); const char *s=va_arg(args,const char*); size_t i=0;
    while(i+1<n && s[i]) {dst[i]=s[i];++i;} if(n) dst[i]=0; va_end(args); return i;
}
static void *heap_caps_malloc(size_t size, int caps) {(void)caps; return size<=sizeof(arena)?arena:NULL;}
static const esp_partition_t *esp_partition_find_first(int type, int sub, const char *label) {(void)type;(void)sub;(void)label;return &partition;}
static int esp_partition_read(const esp_partition_t *p,size_t offset,void *dst,size_t size) {if(offset+size>p->size)return -1;memcpy(dst,flash+offset,size);return 0;}
static int esp_partition_erase_range(const esp_partition_t *p,size_t offset,size_t size) {(void)p;memset(flash+offset,255,size);++erase_count;return 0;}
static int esp_partition_write(const esp_partition_t *p,size_t offset,const void *data,size_t size) {
    if(offset+size>p->size)return -1;
    bool fail=++write_count==fail_write;
    size_t count=fail && fail_bytes<(int)size ? fail_bytes : size;
    for(size_t i=0;i<count;++i)flash[offset+i]&=((const uint8_t*)data)[i];
    return fail?-1:0;
}
static int nvs_open(const char *ns,int mode,nvs_handle_t *h){(void)ns;(void)mode;*h=1;return 0;}
static int nvs_get_u64(nvs_handle_t h,const char *key,uint64_t *v){(void)h;(void)key;*v=attempt_value;return 0;}
static int nvs_set_u64(nvs_handle_t h,const char *key,uint64_t v){(void)h;(void)key;staged_value=v;return 0;}
static int nvs_commit(nvs_handle_t h){(void)h;if(fail_commit)return -1;attempt_value=staged_value;return 0;}

/*ROW_TYPE*/
#include "checkpoint.inc"
#define VERIFY(condition, code) do {if(!(condition))return code;} while(0)

int check(int mode) {
    memset(flash,255,sizeof(flash)); attempt_value=staged_value=0;
    erase_count=write_count=fail_write=fail_bytes=fail_commit=0; identity[6]='1';
    VERIFY(checkpoint_open(),1);
    report_row_t row,out; memset(&row,0,sizeof(row));
    unsigned attempts; bool skip;
    if(mode==0) {
        for(size_t i=0;i<NUM_IMAGES;++i) {
            VERIFY(checkpoint_attempt(i,&attempts,&skip)&&!skip&&attempts==1,2);
            row.result=i; row.ok=1;
            VERIFY(checkpoint_append(i,&row),3);
        }
        VERIFY(checkpoint_open(),4);
        for(size_t i=0;i<NUM_IMAGES;++i) {VERIFY(checkpoint_read(&out)==1,5);VERIFY(out.result==(int)i,6);}
        VERIFY(checkpoint_read(&out)==0&&cp_next==NUM_IMAGES&&erase_count==1,7);
    } else if(mode==1) {
        for(unsigned count=1;count<=RECOVERY_MAX_ATTEMPTS;++count) {
            VERIFY(checkpoint_open()&&checkpoint_read(&out)==0,8);
            VERIFY(checkpoint_attempt(0,&attempts,&skip)&&!skip&&attempts==count,9);
        }
        VERIFY(checkpoint_open()&&checkpoint_read(&out)==0,10);
        VERIFY(checkpoint_attempt(0,&attempts,&skip)&&skip,11);
        row.recovery_skipped=1; VERIFY(checkpoint_append(0,&row),12);
        VERIFY(checkpoint_open()&&checkpoint_read(&out)==1&&out.recovery_skipped==1,13);
        VERIFY(checkpoint_attempt(1,&attempts,&skip)&&!skip&&attempts==1,14);
    } else if(mode==2 || mode==3 || mode==4) {
        row.result=42; VERIFY(checkpoint_append(0,&row),15);
        size_t last=cp_offset;
        fail_write=write_count+(mode==2?1:2); fail_bytes=mode==2?20:mode==4?4:0;
        row.result=43; VERIFY(!checkpoint_append(1,&row),16);
        fail_write=0;
        VERIFY(checkpoint_open()&&checkpoint_read(&out)==1&&out.result==42,17);
        if(mode==4) {VERIFY(checkpoint_read(&out)==1&&out.result==43,18);}
        else {
            VERIFY(checkpoint_read(&out)==0&&cp_offset>last,19);
            VERIFY(checkpoint_append(1,&row),20);
            VERIFY(checkpoint_open()&&checkpoint_read(&out)==1&&out.result==42,21);
            VERIFY(checkpoint_read(&out)==1&&out.result==43,22);
        }
        VERIFY(checkpoint_read(&out)==0&&cp_next==2&&erase_count==1,23);
    } else if(mode==5) {
        VERIFY(checkpoint_append(0,&row),24); identity[6]='2';
        VERIFY(checkpoint_open()&&checkpoint_read(&out)==0&&erase_count==2,25);
    } else if(mode==6) {
        cp_offset=partition.size; VERIFY(!checkpoint_append(0,&row)&&erase_count==1,26);
    } else if(mode==7) {
        fail_commit=1; VERIFY(!checkpoint_attempt(0,&attempts,&skip),27);
        fail_commit=0; VERIFY(checkpoint_open()&&checkpoint_attempt(0,&attempts,&skip)&&attempts==1&&!skip,28);
    }
    return 0;
}
