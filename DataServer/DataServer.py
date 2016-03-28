#!/usr/bin/python3

"""
AUTHOR: Matthew May - mcmay.web@gmail.com
"""

# Imports
import json
#import logging
import maxminddb
#import re
import redis

from const import META, PORTMAP

from argparse import ArgumentParser, RawDescriptionHelpFormatter
from os import getuid
from sys import exit
from textwrap import dedent
from time import gmtime, sleep, strftime

# start the Redis server if it isn't started already.
# $ redis-server
# default port is 6379
# make sure system can use a lot of memory and overcommit memory

redis_ip = '127.0.0.1'
redis_instance = None

# required input paths
syslog_path = '/var/log/syslog'
db_path = '/db-data/GeoLite2-City.mmdb'

# file to log data
log_file_out = '/var/log/map_data_server.out'

# ip for headquarters
hq_ip = '8.8.8.8'

# stats
#server_start_time = strftime("%Y-%m-%d %H:%M:%S", gmtime())
event_count = 0
unknowns = {}
continents_tracked = {}
countries_tracked = {}
ips_tracked = {}


# @IDEA
#---------------------------------------------------------
# Use a class to nicely wrap everything
# You could attempt to do an acces here
# now with worrying about key errors
# Or just keep the filled data structure
#class Instance(dict):
#
#    defaults = {
#                'city': {'names':{'en':None}},
#                'continent': {'names':{'en':None}},
#                'continent': {'code':None},
#                'country': {'names':{'en':None}},
#                'country': {'iso_code':None},
#                'location': {'latitude':None},
#                'location': {'longitude':None},
#                'location': {'metro_code':None},
#                'postal': {'code':None}
#                }
#
#    def __init__(self, seed):
#        self(seed)
#        backfill()
#
#    def backfill(self):
#        for default in self.defaults:
#            if default not in self:
#                self[default] = defaults[default]
#---------------------------------------------------------

# create clean dictionary using unclean db dictionary contents
def clean_db(unclean):
    selected = {}
    for tag in META:
        head = None
        if tag['tag'] in unclean:
            head = unclean[tag['tag']]
            for node in tag['path']:
                if node in head:
                    head = head[node]
                else:
                    head = None
                    break
            selected[tag['lookup']] = head

    return selected


def connect_redis(redis_ip):
    r = redis.StrictRedis(host=redis_ip, port=6379, db=0)
    return r


def get_msg_type():
    # @TODO
    # add support for more message types later
    return "Traffic"

# check to see if packet is using an interesting TCP/UDP protocol based on source or destination port
def get_tcp_udp_proto(src_port, dst_port):
    src_port = int(src_port)
    dst_port = int(dst_port)

    if src_port in PORTMAP:
        return PORTMAP[src_port]
    if dst_port in PORTMAP:
        return PORTMAP[dst_port]

    return "OTHER"


def find_hq_lat_long(hq_ip):
    hq_ip_db_unclean = parse_maxminddb(db_path, hq_ip)
    if hq_ip_db_unclean:
        hq_ip_db_clean = clean_db(hq_ip_db_unclean)
        dst_lat = hq_ip_db_clean['latitude']
        dst_long = hq_ip_db_clean['longitude']
        hq_dict = {
                'dst_lat': dst_lat,
                'dst_long': dst_long
                }
        return hq_dict
    else:
        print('Please provide a valid IP address for headquarters')
        exit()


def parse_maxminddb(db_path, ip):
    try:
        reader = maxminddb.open_database(db_path)
        response = reader.get(ip)
        reader.close()
        return response
    except FileNotFoundError:
        print('DB not found')
        print('SHUTTING DOWN')
        exit()
    except ValueError:
        return False


# @TODO
# refactor/improve parsing
# this function depends heavily on which appliances are generating logs
# for now it is only here for testing
def parse_syslog(line):
    line = line.split()
    data = line[-1]
    data = data.split(',')
    if len(data) != 4:
        print('NOT A VALID LOG')
        return False
    else:
        src_ip = data[0]
        dst_ip = data[1]
        src_port = data[2]
        dst_port = data[3]
        data_dict = {
                    'src_ip': src_ip,
                    'dst_ip': dst_ip,
                    'src_port': src_port,
                    'dst_port': dst_port
                    }
        return data_dict


def shutdown_and_report_stats():
    print('\nSHUTTING DOWN')
    # report stats tracked
    print('\nREPORTING STATS...')
    print('\nEvent Count: {}'.format(event_count)) # report event count
    print('\nContinent Stats...') # report continents stats 
    for key in continents_tracked:
        print('{}: {}'.format(key, continents_tracked[key]))
    print('\nCountry Stats...') # report country stats
    for country in countries_tracked:
        print('{}: {}'.format(country, countries_tracked[country]))
    print('\nIP Stats...') # report IP stats
    for ip in ips_tracked:
        print('{}: {}'.format(ip, ips_tracked[ip]))
    print('\nUnknowns...')
    for key in unknowns:
        print('{}: {}'.format(key, unknowns[key]))
    # log stats tracked
    exit()


def menu():
    # instantiate parser
    parser = ArgumentParser(
            prog='DataServer.py',
            usage='%(progs)s [OPTIONS]',
            formatter_class=RawDescriptionHelpFormatter,
            description=dedent('''\
                    --------------------------------------------------------------
                    Data server for attack map application.
                    --------------------------------------------------------------'''))

    # @TODO --> Add support for command line args?
    # define command line arguments
    # parser.add_argument('-db', '--database', dest='db_path', required=True, type=str, help='path to maxmind database')
    # parser.add_argument('-m', '--readme', dest='readme', help='print readme')
    # parser.add_argument('-o', '--output', dest='output', help='file to write logs to')
    # parser.add_argument('-r', '--random', action='store_true', dest='randomize', help='generate random IPs/protocols for demo')
    # parser.add_argument('-rs', '--redis-server-ip', dest='redis_ip', type=str, help='redis server ip address')
    # parser.add_argument('-sp', '--syslog-path', dest='syslog_path', type=str, help='path to syslog file')
    parser.add_argument('-v', '--verbose', action='store_true', dest='verbose', help='run server in verbose mode')

    # parse arguments/options
    args = parser.parse_args()
    return args


def merge_dicts(*args):
    super_dict = {}
    for arg in args:
        super_dict.update(arg)
    return super_dict


def track_stats(super_dict, tracking_dict, key):
    #global unknowns
    if key in super_dict:
        node = super_dict[key]
        if node in tracking_dict:
            tracking_dict[node] += 1
        else:
            tracking_dict[node] = 1
    else:
        if key in unknowns:
            unknowns[key] += 1
        else:
            unknowns[key] = 1


def main():
    if getuid() != 0:
        print('Please run this script as root')
        print('SHUTTING DOWN')
        exit()

    global db_path, log_file_out, redis_ip, redis_instance, syslog_path, hq_ip
    global continents_tracked, countries_tracked, ips_tracked, postal_codes_tracked, event_count, unknown

    args = menu()

    # connect to Redis
    redis_instance = connect_redis(redis_ip)

    # find HQ lat/long
    hq_dict = find_hq_lat_long(hq_ip)

    # follow/parse/format/publish syslog data
    with open(syslog_path, "r") as syslog_file:
        while True:
            where = syslog_file.tell()
            line = syslog_file.readline()
            if not line:
                sleep(.2)
                syslog_file.seek(where)
            else:
                syslog_data_dict = parse_syslog(line)
                if syslog_data_dict:
                    ip_db_unclean = parse_maxminddb(db_path, syslog_data_dict['src_ip'])
                    if ip_db_unclean:
                        event_count += 1
                        ip_db_clean = clean_db(ip_db_unclean)
                        msg_type = {'msg_type': get_msg_type()}
                        proto = {'protocol': get_tcp_udp_proto(
                                                            syslog_data_dict['src_port'],
                                                            syslog_data_dict['dst_port']
                                                            )}
                        super_dict = merge_dicts(
                                                hq_dict,
                                                ip_db_clean,
                                                msg_type,
                                                proto,
                                                syslog_data_dict
                                                )

                        # Track Stats
                        track_stats(super_dict, continents_tracked, 'continent')
                        track_stats(super_dict, countries_tracked, 'country')
                        track_stats(super_dict, ips_tracked, 'src_ip')
                        event_time = strftime("%Y-%m-%d %H:%M:%S", gmtime())

                        # Append stats to super_dict
                        super_dict['event_count'] = event_count
                        super_dict['continents_tracked'] = continents_tracked
                        super_dict['countries_tracked'] = countries_tracked
                        super_dict['ips_tracked'] = ips_tracked
                        super_dict['unknowns'] = unknowns
                        super_dict['event_time'] = event_time

                        json_data = json.dumps(super_dict)
                        redis_instance.publish('attack-map-production', json_data)

                        if args.verbose:
                            print(ip_db_unclean)
                            print('------------------------')
                            print(json_data)
                            print('Event Count: {}'.format(event_count))
                            print('------------------------')

                        print('Event Count: {}'.format(event_count))
                        print('------------------------')

                    else:
                        continue


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        shutdown_and_report_stats()
