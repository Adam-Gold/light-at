import ConfigParser
import json
import os

from flask import Flask, request
from rq import Queue
from rq.job import Job

import AT
from worker import conn

# Initialize needed objects
app = Flask(__name__)
app.config['DEBUG'] = True

Config = ConfigParser.ConfigParser()
try:
    config_dir, config_filename = os.path.split(__file__)
    config_path = os.path.join(config_dir, "config", "config.ini")
    Config.read(config_path)
except Exception as e:
    app.logger.warn("Failed to read configuration file: %s" % e)

queue = Queue(connection=conn)


def generate_hostaddress(hostname, host_ip, domain):
    ret_val = None

    parts_of_ip = host_ip.split('.')

    if len(parts_of_ip) != 4:
        return ret_val

    last_octet = parts_of_ip[-1]

    ret_val = "%s%s.%s" % (hostname, last_octet, domain)

    return ret_val


@app.route('/ansible/playbook', methods=['POST'])
def playbook():
    install_host = request.form['host']
    install_playbook = request.form['playbook']
    group = request.form['group']

    install_ip = request.remote_addr

    sleep_time = int(Config.get('light-at', 'sleep_time'))

    ansible_remote_user = Config.get('light-at', 'windows_remote_user') if AT.is_windows(group) else \
        Config.get('light-at', 'linux_remote_user')
    ansible_private_key = Config.get('light-at', 'key')
    ansible_connection = 'winrm' if AT.is_windows(group) else 'ssh'
    passwords = dict(vault_pass=Config.get('light-at', 'remote_password')) if \
        AT.is_windows(group) else dict()

    domain = Config.get('light-at', 'domain')
    host_address = generate_hostaddress(install_host, install_ip, domain)

    AT.add_host_to_inventory(host_address, group)

    app.logger.info("POST request received from %s for /ansible/playbook/ with parameters: Host=%s Playbook=%s "
                    "and Group=%s" % (install_ip, install_host, install_playbook, group))
    app.logger.info("Preparing to Queue the Job")

    job = queue.enqueue_call(
        func=AT.ansible_run, args=(host_address, install_ip, install_playbook, group,
                                   ansible_connection, ansible_remote_user, passwords, ansible_private_key,
                                   sleep_time),
        result_ttl=5000, timeout=2000
    )

    if AT.is_windows(group):
        job.meta['host_address'] = host_address.partition('.')[0].upper()
    else:
        job.meta['host_address'] = host_address

    job.save()

    jid = job.get_id()

    if jid:
        app.logger.info("Job Succesfully Queued with JobID: %s" % jid)
    else:
        app.logger.info("Failed to Queue the Job")

    return jid


@app.route("/ansible/hostaddress/<job_key>", methods=['GET'])
def get_hostaddress(job_key):
    job = Job.fetch(job_key, connection=conn)

    return job.meta['host_address']


@app.route("/ansible/results/<job_key>", methods=['GET'])
def get_results(job_key):
    ret_val = None
    job = Job.fetch(job_key, connection=conn)

    if job.is_finished:
        if job.return_value != 0:
            ret_val = {'status': 'failed'}
        else:
            ret_val = {'status': 'finished'}
    elif job.is_queued:
        ret_val = {'status': 'in-queue'}
    elif job.is_started:
        ret_val = {'status': 'waiting'}
    elif job.is_failed:
        ret_val = {'status': 'failed'}

    return json.dumps(ret_val), 200


def main():
    app.run(host='0.0.0.0', port=8000, debug=True)


if __name__ == '__main__':
    main()