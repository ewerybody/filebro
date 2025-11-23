# server.py - Backend server with worker pool
from flask import Flask, request, jsonify
from concurrent.futures import ProcessPoolExecutor
import multiprocessing
import uuid
import subprocess
from pathlib import Path

app = Flask(__name__)

# Worker pool - automatically uses CPU count
executor = ProcessPoolExecutor(max_workers=multiprocessing.cpu_count())

# Track jobs in memory (use Redis/SQLite for persistence)
jobs = {}


# Worker functions - these run in separate processes
def resize_image(job_id, input_path, output_path, width, height):
    from PIL import Image

    try:
        img = Image.open(input_path)
        img = img.resize((width, height))
        img.save(output_path)
        return {'status': 'completed', 'output': output_path}
    except Exception as e:
        return {'status': 'failed', 'error': str(e)}


def encode_video(job_id, input_path, output_path, codec='libx264'):
    try:
        result = subprocess.run(
            [
                'ffmpeg',
                '-i',
                input_path,
                '-c:v',
                codec,
                '-preset',
                'medium',
                output_path,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        return {'status': 'completed', 'output': output_path}
    except subprocess.CalledProcessError as e:
        return {'status': 'failed', 'error': e.stderr}


def ftp_upload(job_id, local_path, remote_host, remote_path, username, password):
    from ftplib import FTP

    try:
        with FTP(remote_host) as ftp:
            ftp.login(username, password)
            with open(local_path, 'rb') as f:
                ftp.storbinary(f'STOR {remote_path}', f)
        return {'status': 'completed', 'remote_path': remote_path}
    except Exception as e:
        return {'status': 'failed', 'error': str(e)}


# Callback when job completes
def job_done_callback(job_id):
    def callback(future):
        try:
            result = future.result()
            jobs[job_id]['status'] = result['status']
            jobs[job_id]['result'] = result
        except Exception as e:
            jobs[job_id]['status'] = 'failed'
            jobs[job_id]['error'] = str(e)

    return callback


# API Endpoints
@app.route('/jobs/resize', methods=['POST'])
def resize_image_job():
    data = request.json
    job_id = str(uuid.uuid4())

    jobs[job_id] = {'id': job_id, 'type': 'resize', 'status': 'pending', 'params': data}

    future = executor.submit(
        resize_image,
        job_id,
        data['input_path'],
        data['output_path'],
        data['width'],
        data['height'],
    )
    future.add_done_callback(job_done_callback(job_id))

    return jsonify({'job_id': job_id})


@app.route('/jobs/encode', methods=['POST'])
def encode_video_job():
    data = request.json
    job_id = str(uuid.uuid4())

    jobs[job_id] = {'id': job_id, 'type': 'encode', 'status': 'pending', 'params': data}

    future = executor.submit(
        encode_video,
        job_id,
        data['input_path'],
        data['output_path'],
        data.get('codec', 'libx264'),
    )
    future.add_done_callback(job_done_callback(job_id))

    return jsonify({'job_id': job_id})


@app.route('/jobs/ftp', methods=['POST'])
def ftp_upload_job():
    data = request.json
    job_id = str(uuid.uuid4())

    jobs[job_id] = {'id': job_id, 'type': 'ftp', 'status': 'pending', 'params': data}

    future = executor.submit(
        ftp_upload,
        job_id,
        data['local_path'],
        data['remote_host'],
        data['remote_path'],
        data['username'],
        data['password'],
    )
    future.add_done_callback(job_done_callback(job_id))

    return jsonify({'job_id': job_id})


@app.route('/jobs/<job_id>', methods=['GET'])
def get_job_status(job_id):
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(jobs[job_id])


@app.route('/jobs', methods=['GET'])
def list_jobs():
    return jsonify(list(jobs.values()))


@app.route('/files/browse', methods=['GET'])
def browse_files():
    path = request.args.get('path', '.')
    try:
        p = Path(path)
        items = []
        for item in p.iterdir():
            items.append(
                {
                    'name': item.name,
                    'path': str(item),
                    'is_dir': item.is_dir(),
                    'size': item.stat().st_size if item.is_file() else None,
                }
            )
        return jsonify({'path': str(p), 'items': items})
    except Exception as e:
        return jsonify({'error': str(e)}), 400


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
