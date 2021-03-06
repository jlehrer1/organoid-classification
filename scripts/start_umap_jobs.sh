#!/bin/bash

for FILE in 'organoid' 'primary'
do
	for N in 15 50 100 500 
	do
		for COMP in 2 3 50 100
		do
			export N=${N} COMP=${COMP} FILE=${FILE} && envsubst < yaml/umap.yaml | kubectl create -f -
		done
	done
done
