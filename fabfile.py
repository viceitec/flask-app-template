from datetime import datetime
from hashlib import md5
from fabric.api import run, local, env, get, put, runs_once, execute
from fabric.contrib.files import exists

PROJECT = 'my_project'
HTTP_PORT = 8000
CONFIG = '/app/settings/prod.py'

if not env.hosts:
    env.hosts = ['host1']

def init():
    run(f'mkdir -p ~/{PROJECT}/images ~/{PROJECT}/data')


def image_hash():
    hsh = md5()
    hsh.update(open('docker/Dockerfile', 'rb').read())
    hsh.update(open('requirements.txt', 'rb').read())
    return hsh.hexdigest()[:10]


@runs_once
def prepare_image():
    hsh = image_hash()
    local(f'''
        docker inspect {PROJECT}:{hsh} > /dev/null || docker build -t {PROJECT}:{hsh} docker
        docker save {PROJECT}:{hsh} | gzip -1 > /tmp/image.tar.gz
    ''')


def push_image():
    hsh = image_hash()
    image_file = f'{PROJECT}/images/{hsh}.tar.gz'
    if not exists(image_file):
        execute(prepare_image)
        put('/tmp/image.tar.gz', image_file)
    run(f'docker load -i {image_file}')


def backup(fname=f'/tmp/{PROJECT}-backup.tar.gz'):
    run(f'tar -C {PROJECT}/data -czf /tmp/backup.tar.gz .')
    get('/tmp/backup.tar.gz', fname)


def restore(fname=f'/tmp/{PROJECT}-backup.tar.gz'):
    put(fname, '/tmp/backup.tar.gz')
    run(f'tar -C {PROJECT}/data xf /tmp/backup.tar.gz .')


@runs_once
def pack_backend():
    hsh = image_hash()
    local(f'''
        echo {hsh} > image.hash
        ( git ls-files && echo image.hash ) | tar czf /tmp/backend.tar.gz -T -
     ''')


def upload():
    version = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    execute(pack_backend)
    put('/tmp/backend.tar.gz', PROJECT)
    run(f'''
        cd {PROJECT}
        mkdir app-{version}
        tar -C app-{version} -xf backend.tar.gz
        ln -snf app-{version} app
    ''')


def restart():
    run(f'''
        docker stop -t 10 {PROJECT}-http
        docker rm {PROJECT}-http || true
        cd {PROJECT}
        docker run -d --name {PROJECT}-http -p {HTTP_PORT}:5000 -e CONFIG={CONFIG} \\
                   -v $PWD/app:/app -v $PWD/data:/data -w /app -u $UID \\
                   {PROJECT}:`cat app/image.hash` uwsgi --ini /app/uwsgi.ini
        sleep 3
        docker logs --tail 10 {PROJECT}-http
    ''')


def shell():
    run(f'''
        cd {PROJECT}
        docker run --rm -e CONFIG={CONFIG} -it \\
                   -v $PWD/app:/app -v $PWD/data:/data -w /app -u $UID \\
                   {PROJECT}:`cat app/image.hash` sh
    ''')