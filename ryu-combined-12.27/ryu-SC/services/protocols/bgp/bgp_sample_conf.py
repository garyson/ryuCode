import os

# =============================================================================
# BGP configuration.
# =============================================================================
BGP = {

    # General BGP configuration.
    'routing': {
        # ASN for this BGP instance.
        'local_as': 20,

        # BGP Router ID.
        'router_id': '1.1.1.1',

        # We list all BGP neighbors below. We establish EBGP sessions with peer
        # with different AS number then configured above. We will
        # establish IBGP session if AS number is same.
        'bgp_neighbors': {
            '10.108.92.1': {
                'remote_as': 10,
                'multi_exit_disc': 100
            },
            '10.108.91.1': {
                'remote_as': 30,
            },
        },

        'networks': [
            '10.108.91.0/24',
            '10.108.92.0/24',

        ],
    },

}


# SSH = {
#     'ssh_port': 4990,
#     'ssh_host': 'localhost',
#     'ssh_hostkey': '/etc/ssh_host_rsa_key',
#     'ssh_username': 'ryu',
#     'ssh_password': 'ryu'
# }

# =============================================================================
# Logging configuration.
# =============================================================================
LOGGING = {

    # We use python logging package for logging.
    'version': 1,
    'disable_existing_loggers': False,

    'formatters': {
        'verbose': {
            'format': '%(levelname)s %(asctime)s %(module)s ' +
                      '[%(process)d %(thread)d] %(message)s'
        },
        'simple': {
            'format': '%(levelname)s %(asctime)s %(module)s %(lineno)s ' +
                      '%(message)s'
        },
        'stats': {
            'format': '%(message)s'
        },
    },

    'handlers': {
        # Outputs log to console.
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'simple'
        },
        'console_stats': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'stats'
        },
        # Rotates log file when its size reaches 10MB.
        'log_file': {
            'level': 'ERROR',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join('.', 'bgpspeaker.log'),
            'maxBytes': '10000000',
            'formatter': 'verbose'
        },
        'stats_file': {
            'level': 'DEBUG',
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': os.path.join('.', 'statistics_bgps.log'),
            'maxBytes': '10000000',
            'formatter': 'stats'
        },
    },

    # Fine-grained control of logging per instance.
    'loggers': {
        'bgpspeaker': {
            'handlers': ['console', 'log_file'],
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
        'stats': {
            'handlers': ['stats_file', 'console_stats'],
            'level': 'INFO',
            'propagate': False,
            'formatter': 'stats',
        },
    },

    # Root loggers.
    'root': {
        'handlers': ['console', 'log_file'],
        'level': 'DEBUG',
        'propagate': True,
    },
}
