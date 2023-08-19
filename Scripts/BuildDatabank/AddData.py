# This is the code that generates databank indexing

# IMPORTING LIBRARIES

from random import randint
import argparse
import yaml
import logging
import shutil
import pprint
from datetime import date
from pathlib import Path

# Working with files and directories
import os

# For quering webs
from urllib.error import URLError, HTTPError

# From time monitoring


# Python program to find SHA256 hash string of a file

# For dealing with excel and cvs
import pandas as pd

pd.set_option("display.max_rows", 500)
pd.set_option("display.max_columns", 500)
pd.set_option("display.width", 1000)
pd.set_option("display.max_colwidth", 1000)

# To make real independent copies of lists
from copy import deepcopy

from MDAnalysis import Universe

# for calculating order parameters
from OrderParameter import *

# from corrtimes import *

import sys

# for building hydrogens to united atom simulations



# import databank dictionaries
from databankLibrary import (
    calc_file_sha1_hash,
    create_databank_directories,
    lipids_dict,
    molecules_dict,
    software_dict,
)


# Download link
from databankLibrary import download_resource_from_uri, parse_valid_config_settings, resolve_download_file_url


# parse input yaml file
parser = argparse.ArgumentParser(
    prog="AddData.py Script", description="Add a new dataset to the NMRLipids databank"
)
parser.add_argument("-f", "--file", help="Input config file in yaml " "format.")
parser.add_argument(
    "-d", "--debug", help="enable debug logging output", action="store_true"
)
parser.add_argument(
    "-n", "--no-cache", help="always redownload repository files", action="store_true"
)
parser.add_argument("-w", "--work-dir", help="override temporary working directory", default="")
parser.add_argument("-o", "--output-dir", help="set output directory", default=os.path.join(Path(os.getcwd()).parents[1].absolute(), "Data", "Simulations"))

args = parser.parse_args()

# configure logging
logging_level = logging.DEBUG if args.debug else logging.INFO
logging.basicConfig(
    format="%(asctime)s [%(levelname)s]: %(message)s",
    datefmt="%m/%d/%Y %I:%M:%S %p",
    level=logging_level,
)
logger = logging.getLogger()

all_molecules = []
for key in lipids_dict:
    all_molecules.append(key)
for key in molecules_dict:
    all_molecules.append(key)

input_path = os.path.join(".", args.file)

#load input yaml file into empty dictionary
info_yaml = {}

#open input file for reading and writing
with open(input_path) as yaml_file:
    info_yaml = yaml.load(yaml_file, Loader=yaml.FullLoader) # TODO may throw yaml.YAMLError
yaml_file.close()

# Show the input read
logger.debug(f"{os.linesep} Input read from {input_path} file:")
pp = pprint.PrettyPrinter(width=41, compact=True)
if logger.isEnabledFor(logging.DEBUG): pp.pprint(yaml.dump(info_yaml))

# validate yaml entries and return updated sim dict
try:
    sim, files = parse_valid_config_settings(info_yaml)

    logger.info(f"all entries in simulation are understood and will be further processed")
    logger.debug("valid sim entry keys:")
    pp = pprint.PrettyPrinter(width=41, compact=True)
    if logger.isEnabledFor(logging.DEBUG): pp.pprint(sim)
except KeyError as e:
    logger.error(f"missing entry key in yaml config: {e}")
    quit()  
except Exception as e:
    logger.error(f"an '{type(e).__name__}' occured while processing '{input_path}', script has been aborted")
    logger.error(e)
    quit()

# Create temporary directory where to download files and analyze them

if args.work_dir:
    dir_wrk = args.work_dir
    logger.warning(f"--work_dir override, ignoring 'DIR_WRK' from configuration file: {sim['DIR_WRK']}")
else:
    dir_wrk = sim["DIR_WRK"]

dir_tmp = os.path.join(dir_wrk, "tmp_6-" + str(randint(100000, 999999))) if args.no_cache else os.path.join(dir_wrk, f"{sim['DOI'].split('/')[-1]}_download")

logger.info(f"The data will be processed in directory path '{dir_tmp}'")

try:
    os.makedirs(dir_tmp, exist_ok=True)
except OSError as e:
    logger.error(f"couldn't create temporary working directory '{dir_tmp}': {e.args[1]}")
    quit()

# Check link status and download files

try:
    download_links = [resolve_download_file_url(sim['DOI'], fi, validate_uri=True) for fi in files]

    logger.info(f"Now downloading {len(files)} files ...")

    for url, fi in zip(download_links, files):
        download_resource_from_uri(url, os.path.join(dir_tmp, fi), override_if_exists=args.no_cache)

    logger.info(f"Download of {len(files)} files was successful")

except HTTPError as e:
    if e.code == 404:
            logger.error(f"ressource not found on server '{e.url}' (404). Wrong DOI link or file name?")
    else:
            logger.error(f"Unexpected HTTPError {e.code} while trying to download the file '{e.url}'")
    quit()
except URLError as e:
    logger.error(f"couldn't resolve network adress: {e.reason}. Please check your internet connection.")
    quit()

# ## Calculate hash of downloaded files

sim_hashes = deepcopy(sim)

software_sim = software_dict[sim["SOFTWARE"].upper()]

# list_containing the sha1 sums for all required files
sha1_list_requied = []

# Make empty dataframe with the desired columns
df_files = pd.DataFrame(columns=["NAME", "TYPE", "REQUIRED", "HASH"], dtype=object)

for key_sim, value_sim in sim_hashes.items():
    # print(f"sim_hashes['{key_sim}'] = {value_sim}")
    try:
        entry_type = software_sim[key_sim]["TYPE"]
        if "file" in entry_type:
            files_list = []
            is_required = software_dict[sim_hashes['SOFTWARE'].upper()][key_sim]['REQUIRED']

            if not is_required and value_sim is None: continue # skip not required NoneType (empty) file entries

            for file_provided in value_sim:
                file_name = os.path.join(dir_tmp, file_provided[0])
                logger.info(f"calculating sha1 hash of '{file_provided[0]}'...")
                file_hash = calc_file_sha1_hash(file_name)
                df_files = df_files.append(
                    {
                        "NAME": file_provided[0],
                        "TYPE": key_sim,
                        "REQUIRED": is_required,
                        "HASH": file_hash,
                    },
                    ignore_index=True,
                )
                files_list.append([file_provided[0], file_hash])

                # Find the keys of the required files to calculate the master_hash
                if is_required: sha1_list_requied.append(file_hash)

                sim_hashes[key_sim] = files_list  # TODO Problematic
    except KeyError as e:  # It is notmal that fails for "ID" and "SOFTWARE"
        continue
print(f"{os.linesep} Summary of downloaded files: ")
print(df_files)

# print("\n{0}\n".format(sha1_list_requied))

# Calculate the hash of a file contaning the hashes of each of the required files
# This should be always invariant as it will be used unique identifier for a simualtion
# Note order the hashes of the required files before calculating the hash (That means that the required files cannot change)
# print(sim_hashes)


# Anne:Read molecule numbers from tpr or gro file.
# Calculates numbers of lipid molecules in each leaflet. This is done by checking on which side of the centre
# of mass the membrane each the centre of mass of a lipid molecule is.
# If a lipid molecule is split so that headgroup and tails are their own residues, the centre of mass of the
# headgroup is used in the calculation.
################################################################################################################

logger.info("Calculating the numbers of lipid molecules in each leaflet based on the center of mass of the membrane and lipids.")
logger.info("If a lipid molecule is split to multiple residues, the centre of mass of the headgroup is used.")

top = ""
traj = ""

# OTHER SOFTWARES THAN GROMACS!!!!
if sim["SOFTWARE"] == "gromacs":
    top = os.path.join(dir_tmp, sim["TPR"][0][0])
    traj = os.path.join(dir_tmp, sim["TRJ"][0][0])
elif sim["SOFTWARE"] == "openMM":
    traj = os.path.join(dir_tmp, sim["TRJ"][0][0])
    top = os.path.join(dir_tmp, sim["PDB"][0][0])


leaflet1 = 0  # total number of lipids in upper leaflet
leaflet2 = 0  # total number of lipids in lower leaflet

# u = Universe(top, traj)
# u.atoms.write(dir_tmp+'/frame0.gro', frames=u.trajectory[[0]]) #write first frame into gro file

gro = os.path.join(dir_tmp, "frame0.gro")
NewTraj = os.path.join(dir_tmp, "NewTraj.xtc")

try:
    u = Universe(top, traj)
    u.atoms.write(gro, frames=u.trajectory[[0]])  # write first frame into gro file
except:
    # conf = str(dir_tmp) + '/conf.gro'
    logger.info(
        "Generating frame0.gro with Gromacs because MDAnalysis cannot read tpr version"
    )
    
    if "WARNINGS" in sim and sim["WARNINGS"]["GROMACS_VERSION"] == "gromacs3":
        os.system(
            "echo System | trjconv -s " + top + " -f " + traj + " -dump 22000 -o " + gro
        )
        # os.system('echo System | trjconv -s '+ top + ' -f '+ traj + ' -o ' + NewTraj)
        # u = Universe(gro, NewTraj)
    else:
        os.system(
            "echo System | gmx trjconv -s " + top + " -f " + traj + " -dump 0 -o " + gro
        )
    u = Universe(gro, traj)
    u.atoms.write(gro, frames=u.trajectory[[0]])  # write first frame into gro file


try:
    groFORu0 = os.path.join(dir_tmp, sim["GRO"][0][0])
    logger.debug(groFORu0)
except:
    groFORu0 = gro

u0 = Universe(groFORu0)
lipids = []

# select lipids
for key_mol in lipids_dict:
    logger.info(f"Calculating number of '{key_mol}' lipids")
    selection = ""
    if key_mol in sim["COMPOSITION"].keys():
        m_file = sim["COMPOSITION"][key_mol]["MAPPING"]
        mapping_dict = {}
        with open(os.path.join(os.getcwd(), "mapping_files", m_file), "r") as yaml_file:
            mapping_dict = yaml.load(yaml_file, Loader=yaml.FullLoader)
        yaml_file.close()
        for key in mapping_dict.keys():
            if "RESIDUE" in mapping_dict[key].keys():
                selection = (
                    selection
                    + "(resname "
                    + mapping_dict[key]["RESIDUE"]
                    + " and name "
                    + mapping_dict[key]["ATOMNAME"]
                    + ") or "
                )
            else:
                selection = "resname " + sim["COMPOSITION"][key_mol]["NAME"]
                break
    #       with open('./mapping_files/'+m_file,"r") as f:
    #           for line in f:
    #               if len(line.split()) > 2 and "Individual atoms" not in line:
    #                   selection = selection + "(resname " + line.split()[2] + " and name " + line.split()[1] + ") or "
    #               elif "Individual atoms" in line:
    #                   continue
    #               else:
    #                   selection = "resname " + sim['COMPOSITION'][key_mol]['NAME']
    #                   #print(selection)
    #                   break
    selection = selection.rstrip(" or ")
    # print("selection    " + selection)
    molecules = u0.select_atoms(selection)
    # print("molecules")
    # print(molecules)
    if molecules.n_residues > 0:
        lipids.append(u0.select_atoms(selection))
        # print(lipids)
# join all the selected the lipids together to make a selection of the entire membrane and calculate the
# z component of the centre of mass of the membrane
membrane = u0.select_atoms("")
R_membrane_z = 0
if lipids != []:
    for i in range(0, len(lipids)):
        membrane = membrane + lipids[i]
        # print("membrane")
        # print(membrane)
    R_membrane_z = membrane.center_of_mass()[2]
logger.info(f"Center of the mass of the membrane: {str(R_membrane_z)}")

#####number of each lipid per leaflet

for key_mol in lipids_dict:
    leaflet1 = 0
    leaflet2 = 0

    selection = ""
    if key_mol in sim["COMPOSITION"].keys():
        m_file = sim["COMPOSITION"][key_mol]["MAPPING"]
        with open(os.path.join(os.getcwd(), "mapping_files", m_file), "r") as yaml_file:
            mapping_dict = yaml.load(yaml_file, Loader=yaml.FullLoader)
        yaml_file.close()
        for key in mapping_dict.keys():
            if "RESIDUE" in mapping_dict[key].keys():
                selection = (
                    selection
                    + "resname "
                    + mapping_dict[key]["RESIDUE"]
                    + " and name "
                    + mapping_dict[key]["ATOMNAME"]
                    + " or "
                )
            else:
                selection = "resname " + sim["COMPOSITION"][key_mol]["NAME"]
                break

    #        with open('./mapping_files/'+m_file,"r") as f:
    #            for line in f:
    #                if len(line.split()) > 2 and "Individual atoms" not in line:
    #                    selection = selection + "resname " + line.split()[2] + " and name " + line.split()[1] + " or "
    #                elif "Individual atoms" in line:
    #                    continue
    #                else:
    #                    selection = "resname " + sim['COMPOSITION'][key_mol]['NAME']
    #                    break
    selection = selection.rstrip(" or ")
    logger.info(selection)
    molecules = u0.select_atoms(selection)
    logger.info(molecules.residues)

    if molecules.n_residues > 0:
        for mol in molecules.residues:
            R = mol.atoms.center_of_mass()

            if R[2] - R_membrane_z > 0:
                leaflet1 = leaflet1 + 1
                # print('layer1  ' + str(leaflet1))
            elif R[2] - R_membrane_z < 0:
                leaflet2 = leaflet2 + 1
                # print('layer2  ' + str(leaflet2))
    try:
        sim["COMPOSITION"][key_mol]["COUNT"] = [leaflet1, leaflet2]
    except KeyError:
        continue
    else:
        logger.info(f"Number of '{key_mol}' in upper leaflet: {str(leaflet1)}")
        logger.info(f"Number of '{key_mol}' in lower leaflet: {str(leaflet2)}")

###########################################################################################
# numbers of other molecules
for key_mol in molecules_dict:
    try:
        mol_name = sim["COMPOSITION"][key_mol]["NAME"]
    except KeyError:
        continue
    else:
        mol_number = u0.select_atoms("resname " + mol_name).n_residues
        sim["COMPOSITION"][key_mol]["COUNT"] = mol_number
        logger.info(f"Number of '{key_mol}': {str(sim['COMPOSITION'][key_mol]['COUNT'])}")

# Anne: Read trajectory size and length

sim["TRAJECTORY_SIZE"] = os.path.getsize(traj)

dt = 0
nsteps = 0
nstxout = 0

Nframes = len(u.trajectory)
timestep = u.trajectory.dt

logger.info(f"Number of frames: {Nframes}")
logger.info(f"Timestep: {timestep}")

trj_length = Nframes * timestep

sim["TRJLENGTH"] = trj_length

# Read temperature from tpr
if sim["SOFTWARE"] == "gromacs":
    file1 = os.path.join(dir_tmp, "tpr.txt")

    logger.info(
        "Exporting information with gmx dump"
    )  # need to get temperature from trajectory not tpr !!!
    if (
        "WARNINGS" in sim
        and "GROMACS_VERSION" in sim["WARNINGS"]
        and sim["WARNINGS"]["GROMACS_VERSION"] == "gromacs3"
    ):
        os.system("echo System | gmxdump -s " + top + " > " + file1)
        TemperatureKey = "ref_t"
    else:
        os.system("echo System | gmx dump -s " + top + " > " + file1)
        TemperatureKey = "ref-t"

    with open(file1, "rt") as tpr_info:
        for line in tpr_info:
            if TemperatureKey in line:
                sim["TEMPERATURE"] = float(line.split()[1])
# read temperature from xml or inp
# elif sim['SOFTWARE'] == 'openMM':
##Use parser written by batuhan to read inp and xml files
#    for key in ['INP','XML']:
#        try:
#            file1 = str(dir_tmp) + '/' + sim[key][0][0]
#        except KeyError:
#            print(key + ' file does not exist')
#            continue
#        else:
#            type = key.lower()
#            sim['TEMPERATURE'] = openmm_parser.openmmParser(file1,type).temperature
#            break

logger.info("Parameters read from input files:")
logger.info(f"TEMPERATURE: {str(sim['TEMPERATURE'])}")
logger.info(f"LENGTH OF THE TRAJECTORY: {str(sim['TRJLENGTH'])}")


## Check that the number of atoms between data and README.yaml match

number_of_atomsTRJ = len(u.atoms)

number_of_atoms = 0
for key_mol in all_molecules:
    mapping_dict = {}
    try:
        mapping_file = os.path.join(
            os.getcwd(), "mapping_files", sim["COMPOSITION"][key_mol]["MAPPING"]
        )
    except:
        continue
    else:
        with open(mapping_file, "r") as yaml_file:
            mapping_dict = yaml.load(yaml_file, Loader=yaml.FullLoader)
        yaml_file.close()

    if sim.get("UNITEDATOM_DICT") and not "SOL" in key_mol:
        mapping_file_length = 0

        for key in mapping_dict.keys():
            if "H" in key:
                continue
            else:
                mapping_file_length += 1

    # if sim.get('UNITEDATOM_DICT') and not 'SOL' in key_mol:
    #    lines = open(mapping_file).readlines(  )
    #    mapping_file_length = 0
    #    for line in lines:
    #        if 'H' in line.split(" ")[0]:
    #            continue
    #        else:
    #            mapping_file_length += 1
    else:
        mapping_file_length = len(mapping_dict.keys())

    try:
        number_of_atoms += (
            np.sum(sim["COMPOSITION"][key_mol]["COUNT"]) * mapping_file_length
        )
    except:
        continue
#    if sim.get('UNITEDATOM_DICT') and not 'SOL' in key_mol:
#        lines = open(mapping_file).readlines(  )
#        mapping_file_length = 0
#        for line in lines:
#            if 'H' in line:
#                continue
#            else:
#                mapping_file_length += 1
#    else:
#        mapping_file_length = len(open(mapping_file).readlines(  ))
#    try:
#        number_of_atoms += np.sum(sim['COMPOSITION'][key_mol]['COUNT']) * mapping_file_length
#    except:
#        continue


if number_of_atoms != number_of_atomsTRJ:
    stop = input(
        f"Number of atoms in trajectory {number_of_atomsTRJ} and README.yaml {number_of_atoms} do no match. Check the mapping files and molecule names. {os.linesep} If you know what you are doing, you can still continue the running the script. Do you want to (y/n)?"
    )
    if stop == "n":
        os._exit("Interrupted because atomnumbers did not match")
    if stop == "y":
        logger.warning(
            "Progressed even thought that atom numbers did not match. CHECK RESULTS MANUALLY!"
        )

sim["NUMBER_OF_ATOMS"] = number_of_atomsTRJ
logger.info(f"Number of atoms in the system: {str(sim['NUMBER_OF_ATOMS'])}")


#####DATE OF RUNNING#####
today = date.today().strftime("%d/%m/%Y")
# print(today)
sim["DATEOFRUNNING"] = today

logger.info(f"Date of adding to the databank: {sim['DATEOFRUNNING']}")

# Type of system is currently hard coded because only lipid bilayers are currently added.
# When we go for other systems, this will be given by user.
sim["TYPEOFSYSTEM"] = "lipid bilayer"

# # Save to databank
# BATUHAN: add openmm parser

directory_path = create_databank_directories(sim, sim_hashes, args.output_dir)

# copy previously downloaded files
logger.info("copying previously downloaded files to databank...")
shutil.copyfile(traj, os.path.join(directory_path, os.path.basename(traj)))
shutil.copyfile(top, os.path.join(directory_path, os.path.basename(top)))

# dictionary saved in yaml format
outfileDICT = os.path.join(dir_tmp, "README.yaml")

logger.info(f"Writing the README.yaml dictionary to '{directory_path}'")

with open(outfileDICT, "w") as f:
    yaml.dump(sim, f, sort_keys=False)
    # why not dump the same file to directory path ?
    shutil.copyfile(
        os.path.join(dir_tmp, "README.yaml"),
        os.path.join(directory_path, "README.yaml"),
    )
