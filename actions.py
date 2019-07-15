from utils import Utils
from db import *
import os
from vms import VMS

vms = VMS()

class Actions(Utils):
    # def container_run(self, image_name, run_cmd, timeout=1800):
    #     """Runs commands on a specific image.

    #     :param image_name: docker image tag.
    #     :type image_name: str
    #     :param run_cmd: command line that will be run tests. 
    #     :type run_cmd: str
    #     :param repo: full repo name
    #     :param timeout: timeout for test.
    #     :type timeout: int
    #     """
    #     container_name = self.random_string()
    #     docker = Docker()
    #     cmd = "/bin/bash -c '{}'".format(run_cmd)
    #     result, stdout = docker.run(
    #         image_name=image_name, name=container_name, command=cmd, environment=self.environment, timeout=timeout
    #     )
    #     xml_path = docker.copy_from(name=container_name, source_path="/test.xml", target_path=self.result_path)
    #     docker.remove_container(container_name)
    #     return result, stdout, xml_path

    def test_run(self, node_ip, port, id):
        """Runs tests with specific commit and store the result in DB.
        
        :param image_name: docker image tag.
        :type image_name: str
        :param id: DB id of this commit details.
        :type id: str
        """
        repo_run = RepoRun.objects.get(id=id)
        status = "success"
        content = self.github_get_content(repo=repo_run.repo, ref=repo_run.commit)
        if content:
            lines = content.splitlines()
            for i, line in enumerate(lines):
                status = "success"
                if line.startswith("#"):
                    continue
                response, stdout, file_path = vms.run_test(run_cmd=line, node_ip=node_ip, port=port)
                if file_path:
                    if response:
                        status = "failure"
                    result = self.xml_parse(path=file_path, line=line)
                    repo_run.result.append(
                        {"type": "testsuite", "status": status, "name": result["summary"]["name"], "content": result}
                    )
                    
                    os.remove(file_path)
                else:
                    if response:
                        status = "failure"
                        name = "cmd {}".format(i + 1)
                    repo_run.result.append({"type": "log", "status": status, "name": name, "content": stdout})
        else:

            repo_run.result.append({"type": "log", "status": status, "name": "No tests", "content": "No tests found"})
        repo_run.save()
        

    def test_black(self, node_ip, port, id):
        """Runs black formatting test on the repo with specific commit.

        :param image_name: docker image tag.
        :type image_name: str
        :param id: DB id of this commit details.
        :type id: str
        """
        repo_run = RepoRun.objects.get(id=id)
        link = self.serverip
        status = "success"
        line = "black {} -l 120 -t py37 --exclude 'templates'".format(self.project_path)
        response, stdout, file = vms.run_test(run_cmd=line, node_ip=node_ip, port=port)
        if "reformatted" in stdout:
            status = "failure"
        repo_run.result.append({"type": "log", "status": status, "name": "Black Formatting", "content": stdout})
        repo_run.save()
        self.github_status_send(
            status=status, link=link, repo=repo_run.repo, commit=repo_run.commit, context="Black-Formatting"
        )

    # def build_image(self, id):
    #     """Builds a docker image using a Dockerfile.

    #     :param id: DB id of this commit details.
    #     :type id: str
    #     :return: image name in case of success.
    #     """
    #     repo_run = RepoRun.objects.get(id=id)
    #     docker = Docker()
    #     image_name = self.random_string()
    #     build_args = {"branch": repo_run.branch, "commit": repo_run.commit}
    #     response = docker.build(image_name=image_name, timeout=1800, docker_file="Dockerfile", build_args=build_args)
    #     if response:
    #         docker.remove_failure_images()
    #         repo_run.status = "error"
    #         repo_run.result.append({"type": "log", "status": "error", "content": response})
    #         repo_run.save()
    #         self.report(id=id)
    #         return False
    #     return image_name

    def cal_status(self, id):
        """Calculates the status of whole tests ran on the BD's id.
        
        :param id: DB id of this commit details.
        :type id: str
        """
        repo_run = RepoRun.objects.get(id=id)
        status = "success"
        for result in repo_run.result:
            if result["status"] != "success":
                status = result["status"]
        repo_run.status = status
        repo_run.save()

    def build_and_test(self, id):
        """Builds, runs tests, calculates status and gives report on telegram and github.
        
        :param id: DB id of this commit details.
        :type id: str
        """
        uuid, node_ip, port = vms.deploy_vm()
        if uuid:
            response = vms.install_app(node_ip=node_ip, port=port, id=id)
            if response:
                self.test_black(node_ip=node_ip, port=port, id=id)
                self.test_run(node_ip=node_ip, port=port, id=id)
                self.cal_status(id=id)
                self.report(id=id)
            vms.destroy_vm(uuid)
        else:
            repo_run = RepoRun.objects.get(id=id)
            repo_run.result.append({"type": "log", "status": "error", "content": "Couldn't deploy a vm"})
            repo_run.save()
            self.cal_status(id=id)