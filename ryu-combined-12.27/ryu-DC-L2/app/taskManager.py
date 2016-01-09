__author__ = 'Johnny'

import random

class TaskPool(object):

    def __init__(self, numbers=100, *args, **kwargs):
        self.TaskPool = []
        self.numbers = numbers
        # self.taskid = 0

    def initTaskPool(self):
        while len(self.TaskPool) < self.numbers:
            item = random.randint(0, 1000)
            if item not in self.TaskPool:
                self.TaskPool.append(item)

    def get_taskid(self):

        taskid = self.TaskPool[0]
        self.TaskPool.remove(taskid)

        return taskid
