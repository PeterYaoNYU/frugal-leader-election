### How to build?
I use the Bazel build system. Any any location, call:
```bash
bazel build //:leader_election
```

### How to run?

I use the ```invoke``` library for running the process. The script is in the subdirectory ```scripts```.
```bash
cd scripts
invoke start
```

To stop the processes from running, 
```bash
killall leader*
```

the command for the ebpf compilation is
```python
sudo python3 loader.py
```