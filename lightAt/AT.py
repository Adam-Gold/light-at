import ConfigParser
import json
import boto
import logging
import sys
import os

from time import sleep
from collections import namedtuple
from ansible.parsing.dataloader import DataLoader
from ansible.vars import VariableManager
from ansible.inventory import Inventory
from ansible.executor.playbook_executor import PlaybookExecutor
from ansible.plugins.callback import CallbackBase


class ResultCallback(CallbackBase):
    """A callback plugin used for performing an action as results come in"""

    def v2_runner_on_ok(self, result, **kwargs):
        """Print a json representation of the result

        This method could store the result in an instance attribute for retrieval later
        """
        host = result._host
        print json.dumps({host.name: result._result}, indent=4)


class EqualsSpaceRemover:
    output_file = None

    def __init__(self, new_output_file):
        self.output_file = new_output_file

    def write(self, what):
        self.output_file.write(what.replace(" = ", "=", 1))


Options = namedtuple('Options', ['listtags', 'listtasks', 'listhosts', 'syntax', 'connection', 'module_path', 'forks',
                                 'remote_user', 'private_key_file', 'become',
                                 'become_method', 'become_user', 'check'])

Config = ConfigParser.ConfigParser()
config_dir, config_filename = os.path.split(__file__)
config_path = os.path.join(config_dir, "config", "config.ini")
Config.read(config_path)

loader = DataLoader()
variable_manager = VariableManager()

loader.set_basedir(Config.get('light-at', 'ansible_roles_path'))

# Instantiate our ResultCallback for handling results as they come in
results_callback = ResultCallback()

logger = logging.getLogger(__name__)
out_handler = logging.StreamHandler(sys.stdout)
out_handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
out_handler.setLevel(logging.INFO)
logger.addHandler(out_handler)
logger.setLevel(logging.INFO)


def is_windows(group):
    for windows_group in Config.get('light-at', 'windows_groups'):
        if windows_group in group:
            return True

    return False


def create_record_set(host_address, host_ip):
    route53_connection = boto.connect_route53(
        aws_access_key_id=Config.get('light-at', 'access_key'),
        aws_secret_access_key=Config.get('light-at', 'secret_key')
    )

    zone = route53_connection.get_zone(Config.get('light-at', 'domain'))

    logger.info("Connected to Route53 using Zone: %s" % zone.name)
    logger.info("Creating A Record for Host: %s with Value: %s" % (host_address, host_ip))

    try:
        status = zone.add_record(
            "A",
            "%s." % host_address,
            host_ip,
            ttl=300
        )
    except Exception as e:
        logger.warning("Couldn't create A record: %s" % e)
        return None

    while status.status != 'INSYNC':
        sleep(10)
        status.update()
        logger.info("A record creation is: %s" % status.status)

    logger.info("A Record %s Created Successfully" % host_address)


def change_aws_name_tag(hostname, host_ip):
    ec2_connection = boto.connect_ec2(
        aws_access_key_id=Config.get('light-at', 'access_key'),
        aws_secret_access_key=Config.get('light-at', 'secret_key')
    )

    filters = {"private-ip-address": host_ip}
    result_list = ec2_connection.get_only_instances(filters=filters)

    logger.info("Changing the Tag Name of: %s to %s" % (host_ip, hostname))

    if isinstance(result_list, list) and len(result_list) > 0:
        instance = result_list[0]

        instance.remove_tag('Name')
        instance.add_tag('Name', hostname)
        logger.info("Name Tag of %s Changed Successfully" % hostname)


def add_host_to_inventory(hostname, group):
    inventory = Inventory(
        loader=loader,
        variable_manager=variable_manager,
        host_list=Config.get('light-at', 'inventory_path')
    )
    variable_manager.set_inventory(inventory)

    if not isinstance(inventory, Inventory):
        return dict()

    try:
        inventory.get_group(group)
    except:
        inventory.add_group(group)

    if any(str(host) in hostname for host in inventory.get_group(group).hosts):
        return dict()
    else:
        logger.info("Adding Host: %s to Inventory in Group: %s" % (hostname, group))
        inventory_update = ConfigParser.ConfigParser(allow_no_value=True)
        inventory_update.read(Config.get('light-at', 'inventory_path'))

        inventory_update.set(group, hostname)

        with open(Config.get('light-at', 'inventory_path'), 'w') as f:
            inventory_update.write(EqualsSpaceRemover(f))

        logger.info("Host: %s Added Successfully to Inventory" % hostname)


def ansible_run(ansible_install_host, install_ip, ansible_install_playbook, ansible_group,
                ansible_connection, remote_user, passwords, private_key, sleep_time):
    if Config.has_option('light-at', 'access_key'):
        create_record_set(ansible_install_host, install_ip)
        change_aws_name_tag(ansible_install_host, install_ip)

    if is_windows(ansible_group):
        sleep(int(sleep_time + 60))
    else:
        sleep(sleep_time)

    inventory = Inventory(
        loader=loader,
        variable_manager=variable_manager,
        host_list=Config.get('light-at', 'inventory_path')
    )

    variable_manager.set_inventory(inventory)

    inventory.subset(ansible_install_host)

    options = Options(
        listtags=False,
        listtasks=False,
        listhosts=False,
        syntax=False,
        connection=ansible_connection,
        module_path='',
        forks=100,
        remote_user=remote_user,
        private_key_file=private_key,
        become=False,
        become_method='sudo',
        become_user='root',
        check=False
    )

    playbook_source = "%s/ansible/%s.yml" % (Config.get('light-at', 'ansible_base'), ansible_install_playbook)

    logger.info("Running Ansible Playbook %s on Host: %s,\nwith the "
                "following arguments:\nGroup=%s\nConnection=%s\nUser=%s" % (ansible_install_playbook,
                                                                            ansible_install_host, ansible_group,
                                                                            ansible_connection, remote_user))
    # Actually run it
    playbook_executor = PlaybookExecutor(
        playbooks=[playbook_source],
        inventory=inventory,
        variable_manager=variable_manager,
        loader=loader,
        options=options,
        passwords=passwords
    )

    result = playbook_executor.run()

    return result
