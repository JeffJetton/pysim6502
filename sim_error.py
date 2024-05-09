################################################################################
#
#   SimError Class
#
#   Custom Exception used to distinguish between errors happening in the
#   simulated system--which drop the user back to the simulator prompt--and
#   actual, Python-level errors--which exit Python entirely.
#
################################################################################

class SimError(Exception):
    
    def __init__(self, *args):
        if args:
            self.message = args[0]
        else:
            self.message = None
            
    def __str__(self):
        if self.message:
            return 'SimError: ' + self.message
        else:
            return 'SimError'